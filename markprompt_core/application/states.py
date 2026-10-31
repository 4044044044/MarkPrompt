"""Business modes and their allowed parent-child relationships."""
from dataclasses import dataclass, field


class StateError(ValueError):
    pass


@dataclass
class ModeFrame:
    kind: str
    payload: dict = field(default_factory=dict)

    def __init__(self, kind, **payload):
        self.kind, self.payload = kind, payload


class BusinessStates:
    ROOTS = frozenset({'open', 'search', 'append', 'find'})
    CHILDREN = {'open': frozenset({'append'}), 'find': frozenset({'open'})}
    MAX_DEPTH = 2  # Two levels. Inception can keep the rest.

    def __init__(self):
        self._frames = []
        self.confirmation = None

    @property
    def frames(self):
        return list(self._frames)

    @property
    def top(self):
        return self.confirmation or (self._frames[-1] if self._frames else None)

    @property
    def active(self):
        return self._frames[-1].kind if self._frames else None

    def has(self, kind):
        if kind == 'confirm':
            return self.confirmation is not None
        return any(frame.kind == kind for frame in self._frames)

    def push(self, kind, **payload):
        if kind == 'confirm':
            if self.confirmation:
                raise StateError('A confirmation is already active')
            self.confirmation = ModeFrame(kind, **payload)
            return
        if kind not in self.ROOTS:
            raise StateError('Unknown business state: ' + kind)
        if self.confirmation:
            raise StateError('Finish the confirmation first')
        if self.active == kind:
            return
        if self._frames:
            if len(self._frames) >= self.MAX_DEPTH:
                raise StateError('Business states are limited to two levels')
            if kind not in self.CHILDREN.get(self.active, ()):
                raise StateError('Unsupported child: %s -> %s' % (self.active, kind))
        self._frames.append(ModeFrame(kind, **payload))

    def pop(self):
        if self.confirmation:
            frame, self.confirmation = self.confirmation, None
            return frame
        return self._frames.pop() if self._frames else None

    def remove(self, kind):
        if kind == 'confirm':
            self.confirmation = None
            return
        index = next((i for i, frame in enumerate(self._frames) if frame.kind == kind), None)
        if index is not None:
            # Never leave a child detached from its parent.
            del self._frames[index:]

    def clear(self):
        self._frames.clear()
        self.confirmation = None

