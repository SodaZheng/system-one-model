#!/usr/bin/env python3
"""Convert one OCI image archive to the manifest.json-based Docker save format.

No extraction to arbitrary filesystem paths, no daemon, and no third-party Python
dependencies. Original config and uncompressed layer bytes are preserved. Both
OCI descriptors and image-config DiffIDs are checked before publishing output.

Format: https://github.com/moby/docker-image-spec/blob/main/spec.md
Usage: python3 scripts/oci_to_docker.py input.oci.tar output.docker.tar --tag repo:tag
"""
import argparse
import contextlib
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

INDEX_TYPES = {
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
}
MANIFEST_TYPES = {
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
}
RAW_TYPES = {
    "application/vnd.oci.image.layer.v1.tar",
    "application/vnd.oci.image.layer.nondistributable.v1.tar",
    "application/vnd.docker.image.rootfs.diff.tar",
}
GZIP_TYPES = {
    "application/vnd.oci.image.layer.v1.tar+gzip",
    "application/vnd.oci.image.layer.nondistributable.v1.tar+gzip",
    "application/vnd.docker.image.rootfs.diff.tar.gzip",
    "application/vnd.docker.image.rootfs.foreign.diff.tar.gzip",
}
ZSTD_TYPES = {
    "application/vnd.oci.image.layer.v1.tar+zstd",
    "application/vnd.oci.image.layer.nondistributable.v1.tar+zstd",
}
CHUNK = 4 * 1024 * 1024


def split_digest(value):
    if not isinstance(value, str) or not re.fullmatch(r"sha(?:256|512):[0-9a-f]+", value):
        raise ValueError(f"Unsupported or malformed digest: {value!r}")
    algorithm, hexadecimal = value.split(":", 1)
    if len(hexadecimal) != hashlib.new(algorithm).digest_size * 2:
        raise ValueError(f"Invalid digest length: {value}")
    return algorithm, hexadecimal


def copy_hash(source, destination, algorithm="sha256"):
    digest = hashlib.new(algorithm)
    size = 0
    while chunk := source.read(CHUNK):
        destination.write(chunk)
        digest.update(chunk)
        size += len(chunk)
    return size, f"{algorithm}:{digest.hexdigest()}"


class Archive:
    def __init__(self, archive):
        self.archive = archive
        self.members = {}
        for member in archive.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"Unsafe archive member: {member.name!r}")
            name = str(path)
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError(f"Non-regular archive member: {member.name!r}")
            if name in self.members:
                raise ValueError(f"Duplicate archive member: {name!r}")
            self.members[name] = member

    def open(self, name):
        if name not in self.members:
            raise ValueError(f"Missing archive member: {name}")
        return self.archive.extractfile(self.members[name])

    def read_json(self, name, descriptor=None):
        if self.members.get(name) is None or self.members[name].size > 16 * 1024 * 1024:
            raise ValueError(f"Missing or oversized JSON member: {name}")
        with self.open(name) as source:
            data = source.read()
        if descriptor:
            self.check_bytes(data, descriptor)
        return json.loads(data), data

    @staticmethod
    def check_bytes(data, descriptor):
        algorithm, _ = split_digest(descriptor["digest"])
        actual = f"{algorithm}:{hashlib.new(algorithm, data).hexdigest()}"
        if len(data) != descriptor["size"] or actual != descriptor["digest"]:
            raise ValueError(f"Descriptor size/digest mismatch: {descriptor['digest']}")

    @staticmethod
    def blob_name(descriptor):
        algorithm, hexadecimal = split_digest(descriptor["digest"])
        if not isinstance(descriptor.get("size"), int) or descriptor["size"] < 0:
            raise ValueError("Descriptor size must be a nonnegative integer")
        return f"blobs/{algorithm}/{hexadecimal}"

    def blob_json(self, descriptor):
        return self.read_json(self.blob_name(descriptor), descriptor)

    def find_images(self, index, desired_platform, depth=0):
        if depth > 8:
            raise ValueError("OCI index nesting is too deep")
        found = []
        for descriptor in index.get("manifests", []):
            platform = descriptor.get("platform", {})
            if platform.get("os") not in (None, desired_platform[0]):
                continue
            if platform.get("architecture") not in (None, desired_platform[1]):
                continue
            kind = descriptor.get("mediaType")
            if kind in INDEX_TYPES:
                nested, _ = self.blob_json(descriptor)
                found.extend(self.find_images(nested, desired_platform, depth + 1))
            elif kind in MANIFEST_TYPES:
                manifest, _ = self.blob_json(descriptor)
                config, config_bytes = self.blob_json(manifest["config"])
                if (config.get("os"), config.get("architecture")) == desired_platform:
                    found.append((manifest, config, config_bytes))
        return found


def add_bytes(archive, name, data):
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mode = 0o644
    archive.addfile(info, io.BytesIO(data))


def convert(source, destination, tag, platform="linux/amd64"):
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve():
        raise ValueError("Input and output must be different files")
    if destination.exists():
        raise ValueError(f"Refusing to overwrite existing output: {destination}")
    parts = tuple(platform.split("/"))
    if len(parts) != 2:
        raise ValueError("Platform must have the form os/architecture")
    if not tag or "@" in tag or any(c.isspace() for c in tag):
        raise ValueError("--tag must be a repository tag, without whitespace or a digest")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.ExitStack() as stack:
        incoming = stack.enter_context(tarfile.open(source, "r:*"))
        oci = Archive(incoming)
        layout, _ = oci.read_json("oci-layout")
        if layout.get("imageLayoutVersion") != "1.0.0":
            raise ValueError("Unsupported OCI layout version")
        index, _ = oci.read_json("index.json")
        images = oci.find_images(index, parts)
        if len(images) != 1:
            raise ValueError(f"Expected exactly one {platform} image; found {len(images)}")
        manifest, config, config_bytes = images[0]
        layers = manifest.get("layers", [])
        rootfs = config.get("rootfs", {})
        diff_ids = rootfs.get("diff_ids", [])
        if rootfs.get("type") != "layers" or len(layers) != len(diff_ids):
            raise ValueError("Config rootfs and manifest layer count do not agree")
        config_digest = hashlib.sha256(config_bytes).hexdigest()
        config_name = f"{config_digest}.json"
        stage = Path(stack.enter_context(tempfile.TemporaryDirectory(
            prefix="oci-convert-", dir=destination.parent)))
        temporary_output = stage / "docker.tar"
        with tarfile.open(temporary_output, "w", format=tarfile.PAX_FORMAT) as outgoing:
            add_bytes(outgoing, config_name, config_bytes)
            output_layers = []
            for number, (descriptor, diff_id) in enumerate(zip(layers, diff_ids), 1):
                algorithm, _ = split_digest(descriptor["digest"])
                raw_algorithm, _ = split_digest(diff_id)
                compressed = stage / "input.layer"
                plain = stage / "layer.tar"
                with oci.open(oci.blob_name(descriptor)) as src, compressed.open("wb") as dst:
                    size, actual = copy_hash(src, dst, algorithm)
                if size != descriptor["size"] or actual != descriptor["digest"]:
                    raise ValueError(f"Layer {number} descriptor size/digest mismatch")
                kind = descriptor.get("mediaType")
                if kind in RAW_TYPES:
                    compressed.rename(plain)
                elif kind in GZIP_TYPES:
                    with gzip.open(compressed, "rb") as src, plain.open("wb") as dst:
                        shutil.copyfileobj(src, dst, CHUNK)
                    compressed.unlink()
                elif kind in ZSTD_TYPES:
                    zstd = shutil.which("zstd")
                    if not zstd:
                        raise ValueError("Zstd-compressed OCI layer requires the zstd command; gzip and raw layers need no dependencies")
                    with plain.open("wb") as dst:
                        subprocess.run([zstd, "-d", "-q", "-c", str(compressed)], stdout=dst, check=True)
                    compressed.unlink()
                else:
                    raise ValueError(f"Unsupported layer media type: {kind!r}")
                with plain.open("rb") as src, open(os.devnull, "wb") as null:
                    _, actual = copy_hash(src, null, raw_algorithm)
                if actual != diff_id:
                    raise ValueError(f"Layer {number} uncompressed DiffID mismatch")
                # Validate tar structure without unpacking or following symlinks.
                with tarfile.open(plain, "r:") as layer_tar:
                    for _ in layer_tar:
                        pass
                name = f"layers/{number:04d}-{diff_id.split(':')[1]}/layer.tar"
                info = tarfile.TarInfo(name)
                info.size = plain.stat().st_size
                info.mode = 0o644
                with plain.open("rb") as src:
                    outgoing.addfile(info, src)
                output_layers.append(name)
                plain.unlink()
                print(f"Verified layer {number}/{len(layers)}: {diff_id}", flush=True)
            docker_manifest = [{"Config": config_name, "RepoTags": [tag], "Layers": output_layers}]
            add_bytes(outgoing, "manifest.json", json.dumps(docker_manifest, separators=(",", ":")).encode())
        # Never publish a partial archive. Refuse replacement even if a competing
        # process created the destination while conversion was running.
        os.link(temporary_output, destination)
        return {"image_id": f"sha256:{config_digest}", "tag": tag,
                "platform": platform, "layers": len(layers),
                "bytes": destination.stat().st_size, "output": str(destination)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    parser.add_argument("destination")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--platform", default="linux/amd64")
    args = parser.parse_args()
    try:
        result = convert(args.source, args.destination, args.tag, args.platform)
    except (ValueError, KeyError, OSError, EOFError, tarfile.TarError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Conversion failed: {exc}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
