"""Bounded regular-file reads and fail-closed bundle publication."""

from __future__ import annotations

import os
from pathlib import Path
import stat
from typing import Mapping

from planforge.model import ContractError


def read_regular(path: Path, maximum_bytes: int) -> bytes:
    try:
        before = path.lstat()
    except OSError as error:
        raise ContractError("input is unavailable") from error
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_size > maximum_bytes
    ):
        raise ContractError("input must be one bounded regular file")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            identity = (before.st_dev, before.st_ino, before.st_size)
            if (opened.st_dev, opened.st_ino, opened.st_size) != identity:
                raise ContractError("input identity changed before reading")
            chunks: list[bytes] = []
            remaining = maximum_bytes + 1
            while remaining:
                chunk = os.read(descriptor, min(65_536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            payload = b"".join(chunks)
            after = os.fstat(descriptor)
            if (
                (after.st_dev, after.st_ino, after.st_size) != identity
                or len(payload) > maximum_bytes
                or len(payload) != before.st_size
            ):
                raise ContractError("input changed or exceeded its bound")
            return payload
        finally:
            os.close(descriptor)
    except OSError as error:
        raise ContractError("input could not be read safely") from error


def publish_bundle(output: Path, files: Mapping[str, bytes]) -> None:
    if not files or any(
        not name or "/" in name or "\\" in name or name in {".", ".."}
        for name in files
    ):
        raise ContractError("bundle inventory is invalid")
    parent = output.parent
    try:
        parent_state = parent.lstat()
    except OSError as error:
        raise ContractError("bundle parent is unavailable") from error
    if not stat.S_ISDIR(parent_state.st_mode) or parent.is_symlink():
        raise ContractError("bundle parent must be a real directory")

    created: list[Path] = []
    try:
        os.mkdir(output, 0o700)
        os.chmod(output, 0o700, follow_symlinks=False)
        for name in sorted(files):
            target = output / name
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(target, flags, 0o600)
            try:
                view = memoryview(files[name])
                while view:
                    written = os.write(descriptor, view)
                    if written <= 0:
                        raise ContractError("bundle write was incomplete")
                    view = view[written:]
                os.fchmod(descriptor, 0o600)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            created.append(target)
        directory = os.open(output, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except (OSError, ContractError) as error:
        for target in reversed(created):
            try:
                target.unlink()
            except OSError:
                pass
        try:
            output.rmdir()
        except OSError:
            pass
        if isinstance(error, ContractError):
            raise
        raise ContractError("bundle could not be published without clobbering") from error


def read_bundle(output: Path, names: frozenset[str], limits: Mapping[str, int]) -> dict[str, bytes]:
    try:
        state = output.lstat()
        inventory = {entry.name for entry in output.iterdir()}
    except OSError as error:
        raise ContractError("bundle is unavailable") from error
    if not stat.S_ISDIR(state.st_mode) or output.is_symlink() or inventory != names:
        raise ContractError("bundle inventory does not match the contract")
    return {name: read_regular(output / name, limits[name]) for name in sorted(names)}
