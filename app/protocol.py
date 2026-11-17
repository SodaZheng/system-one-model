"""TypeSafe text primitives. Wire contract follows the checked-in upstream OpenAPI."""
import json
import math
import re
from types import SimpleNamespace
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, JsonValue

MODEL = 'this-that-model-1.2'
Description = str | dict[str, JsonValue] | list[JsonValue]

class APIError(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message
        super().__init__(message)

class QuestionBase(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    instructions: Description | None = None

class Choice(QuestionBase):
    type: Literal['choice']
    criteria: dict[str, Description | None] = Field(min_length=1, max_length=255)

class Score(QuestionBase):
    type: Literal['score']
    criteria: list[Description] = Field(min_length=1, max_length=10)

class NoulCriteria(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    true: Description | None = None
    false: Description | None = None

class Noul(QuestionBase):
    type: Literal['noul']
    criteria: NoulCriteria | None = None

Question = Annotated[Choice | Score | Noul, Field(discriminator='type')]

class RequestBody(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    model: str = 'jev-latest'
    state: Description
    questions: dict[str, Question] = Field(min_length=1, max_length=256)
    assets: dict | None = None


def semantic(value):
    if value is None: return ''
    if isinstance(value, str): return value
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def resolve_model(name):
    if name in {MODEL, 'thisthat', 'thisthat-1.2', 'flock-io/this-that-model-1.2', 'jev', 'jev-latest', 'jev-preview'}:
        return MODEL
    # Published Jev version names are compatibility aliases, never an identity claim.
    if re.fullmatch(r'jev-\d+(?:\.\d+)*(?:-[a-z0-9]+)*', name): return MODEL
    raise APIError(404, 'model_not_found', f'Unknown model: {name[:100]}')


def question_parts(question):
    if question.type == 'noul':
        criteria = question.criteria or NoulCriteria()
        return ['false', 'true'], [semantic(criteria.false) or 'no', semantic(criteria.true) or 'yes']
    if question.type == 'score':
        return [str(i) for i in range(len(question.criteria))], list(map(semantic, question.criteria))
    keys = list(question.criteria)
    return keys, [key if desc is None else f'{key}: {semantic(desc)}' for key, desc in question.criteria.items()]


def encode(tokenizer, body, max_tokens=32768):
    from thisthat.prompt import build
    resolve_model(body.model)
    if body.assets:
        raise APIError(422, 'unsupported_modality', 'THIS/THAT 1.2 supports text only; image assets are not supported.')
    questions, keys = [], []
    for q in body.questions.values():
        labels, options = question_parts(q)
        keys.append(labels)
        questions.append(SimpleNamespace(text=semantic(q.instructions), options=options))
    state = semantic(body.state)
    # Upstream defaults to truncation. Supply a proven upper bound so nothing is sliced off.
    state_tokens = len(tokenizer.encode('Context:\n' + state, add_special_tokens=False))
    if state_tokens > max_tokens:
        raise APIError(422, 'max_tokens_exceeded', f'State alone uses {state_tokens} tokens; limit {max_tokens}. No truncation.')
    built = build(tokenizer, state, questions, max_state_tokens=state_tokens + 16)
    if len(built['ids']) > max_tokens:
        raise APIError(422, 'max_tokens_exceeded', f'Complete input uses {len(built["ids"])} tokens; limit {max_tokens}, including all questions and criteria. No truncation.')
    return built, keys


def render(question, keys, probabilities):
    if len(keys) != len(probabilities) or any(not math.isfinite(p) or p < 0 for p in probabilities):
        raise RuntimeError('Invalid model probabilities')
    total = sum(probabilities)
    if total <= 0: raise RuntimeError('Empty model probability mass')
    p = [x / total for x in probabilities]
    if question.type == 'noul': return {'type': 'noul', 'noul': p[1]}
    # Exact published TypeSafe confidence formulas (docs/upstream/confidence.md).
    n = len(p)
    if n == 1:
        confidence = 1.0
    elif question.type == 'choice':
        confidence = (max(p) - 1 / n) / (1 - 1 / n)
    else:
        mode = max(range(n), key=p.__getitem__)
        spread = sum(x * abs(i - mode) for i, x in enumerate(p))
        even_spread = sum(abs(i - (n - 1) / 2) for i in range(n)) / n
        confidence = max(0., 1 - spread / even_spread)
    result = {'type': question.type, 'probabilities': dict(zip(keys, p)),
              'confidence': min(1., max(0., confidence))}
    if question.type == 'choice': result['choice'] = keys[max(range(len(p)), key=p.__getitem__)]
    else:
        result['score'] = sum(i * x for i, x in enumerate(p))
        result['legend'] = dict(zip(keys, question.criteria))
    return result
