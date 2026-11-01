"""In-memory TrackAttributes store with strict known/unknown semantics.

Pure logic store. No DB, no disk, no network, no clocks.
Timestamps are always passed explicitly.
"""

from typing import Any

from app.core.types import AttrValue, TrackAttributes


class AttributeStore:
    """Manages TrackAttributes for active tracks."""

    def __init__(self):
        self._tracks: dict[int, TrackAttributes] = {}

    def get(self, track_id: int) -> TrackAttributes | None:
        """Get attributes for a track, if registered."""
        return self._tracks.get(track_id)

    def get_or_create(self, track_id: int, kind: str) -> TrackAttributes:
        """Get existing track attributes or create a new empty record."""
        if track_id not in self._tracks:
            self._tracks[track_id] = TrackAttributes(track_id=track_id, kind=kind, attrs={})
        return self._tracks[track_id]

    def set_attr(
        self,
        track_id: int,
        kind: str,
        name: str,
        value: Any,
        conf: float,
        state: str,
        ts_ms: int
    ) -> TrackAttributes:
        """Update or set an attribute for a track.
        
        state must be 'known' or 'unknown'.
        Increments n_obs if the attribute already existed.
        """
        if state not in ("known", "unknown"):
            raise ValueError(f"State must be 'known' or 'unknown', got {state}")

        track = self.get_or_create(track_id, kind)
        existing = track.attrs.get(name)
        n_obs = (existing.n_obs + 1) if existing is not None else 1

        new_attr = AttrValue(
            value=value,
            conf=float(conf),
            state=state,
            n_obs=n_obs,
            updated_ms=ts_ms
        )

        new_attrs = dict(track.attrs)
        new_attrs[name] = new_attr

        updated_track = TrackAttributes(
            track_id=track_id,
            kind=kind,
            attrs=new_attrs
        )
        self._tracks[track_id] = updated_track
        return updated_track

    def get_attr(self, track_id: int, name: str) -> AttrValue | None:
        """Get a specific AttrValue for a track."""
        track = self.get(track_id)
        if track is None:
            return None
        return track.attrs.get(name)

    def is_known(self, track_id: int, name: str) -> bool:
        """Return True only if the attribute exists and has state == 'known'."""
        attr = self.get_attr(track_id, name)
        if attr is None:
            return False
        return attr.state == "known"

    def get_known_value(self, track_id: int, name: str) -> Any | None:
        """Return the value only if state == 'known', else None."""
        attr = self.get_attr(track_id, name)
        if attr is not None and attr.state == "known":
            return attr.value
        return None

    def remove_track(self, track_id: int) -> None:
        """Remove a track when lost or finalized."""
        self._tracks.pop(track_id, None)

    def clear(self) -> None:
        """Clear all tracks."""
        self._tracks.clear()

    def snapshot(self, track_id: int) -> dict[str, Any]:
        """Return a clean JSON-serializable snapshot of track attributes."""
        track = self.get(track_id)
        if track is None:
            return {}
        result: dict[str, Any] = {"kind": track.kind}
        for name, attr in track.attrs.items():
            result[name] = {
                "value": attr.value,
                "conf": attr.conf,
                "state": attr.state,
                "n_obs": attr.n_obs,
                "updated_ms": attr.updated_ms
            }
        return result

    def all_attrs(self) -> dict[int, TrackAttributes]:
        """Return a copy of all current TrackAttributes."""
        return dict(self._tracks)
