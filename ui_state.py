from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(slots=True)
class UiError:
    title: str
    message: str
    recovery_action: str = "Retry"
    category: str = "unknown"


@dataclass(slots=True)
class Idle:
    kind: str = "idle"


@dataclass(slots=True)
class Loading:
    message: str = "Loading..."
    kind: str = "loading"


@dataclass(slots=True)
class Success(Generic[T]):
    data: T
    kind: str = "success"


@dataclass(slots=True)
class Empty:
    title: str = "Nothing here yet"
    message: str = "Try a different action."
    kind: str = "empty"


@dataclass(slots=True)
class Error:
    error: UiError
    kind: str = "error"


UiState = Idle | Loading | Success[T] | Empty | Error


@dataclass
class UiStateMachine(Generic[T]):
    state: UiState[T] = field(default_factory=Idle)
    history: list[str] = field(default_factory=lambda: ["idle"])

    def set_state(self, state: UiState[T]) -> UiState[T]:
        self.state = state
        self.history.append(state.kind)
        return state

    def to_idle(self) -> UiState[T]:
        return self.set_state(Idle())

    def to_loading(self, message: str = "Loading...") -> UiState[T]:
        return self.set_state(Loading(message=message))

    def to_success(self, data: T) -> UiState[T]:
        return self.set_state(Success(data=data))

    def to_empty(self, title: str, message: str) -> UiState[T]:
        return self.set_state(Empty(title=title, message=message))

    def to_error(self, error: UiError) -> UiState[T]:
        return self.set_state(Error(error=error))
