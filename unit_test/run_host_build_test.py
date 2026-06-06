"""Tests for the shared host build driver's stage gating."""

# The fake backend below deliberately ignores most of its arguments.
# ruff: noqa: ARG002

from __future__ import annotations

import dataclasses
from typing import cast

import pytest

from cibuildwheel import errors
from cibuildwheel.platforms._run import Stage, run_host_build

TYPE_CHECKING = False
if TYPE_CHECKING:
    from pathlib import Path

    from cibuildwheel.options import Options


@dataclasses.dataclass
class FakeBuildOptions:
    output_dir: Path
    audit_command: list[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class FakeGlobals:
    build_selector: object = None
    architectures: set[object] = dataclasses.field(default_factory=set)


class FakeOptions:
    def __init__(self, output_dir: Path) -> None:
        self.globals = FakeGlobals()
        self._build_options = FakeBuildOptions(output_dir=output_dir)

    def build_options(self, identifier: str | None) -> FakeBuildOptions:
        return self._build_options


@dataclasses.dataclass
class FakeConfig:
    identifier: str


class FakeBackend:
    """A HostBackend recording which phases the driver invokes."""

    def __init__(self, configs: list[FakeConfig], built_wheel: Path) -> None:
        self.configs = configs
        self.built_wheel = built_wheel
        self.calls: list[object] = []

    def get_python_configurations(
        self, build_selector: object, architectures: object
    ) -> list[FakeConfig]:
        return self.configs

    def before_all(self, options: object, configs: object) -> None:
        self.calls.append("before_all")

    def setup(self, config: FakeConfig, options: object, tmp_path: Path) -> FakeConfig:
        self.calls.append("setup")
        return config

    def before_build(self, state: object) -> None:
        self.calls.append("before_build")

    def build_wheel(self, state: object) -> Path:
        self.calls.append("build_wheel")
        self.built_wheel.write_bytes(b"")
        return self.built_wheel

    def repair_wheel(self, state: object, built_wheel: Path) -> Path:
        self.calls.append("repair_wheel")
        return built_wheel

    def test_wheel(self, state: object, wheel: Path) -> None:
        self.calls.append(("test_wheel", wheel.name))

    def teardown(self, state: object) -> None:
        self.calls.append("teardown")


WHEEL_NAME = "foo-1.0-cp311-cp311-manylinux2014_x86_64.whl"
IDENTIFIER = "cp311-manylinux_x86_64"


def _options(output_dir: Path) -> Options:
    return cast("Options", FakeOptions(output_dir))


def test_run_host_build_all_stages(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    backend = FakeBackend([FakeConfig(IDENTIFIER)], tmp_path / WHEEL_NAME)

    run_host_build(backend, _options(output_dir), tmp_path)

    assert backend.calls == [
        "before_all",
        "setup",
        "before_build",
        "build_wheel",
        "repair_wheel",
        ("test_wheel", WHEEL_NAME),
        "teardown",
    ]
    # the wheel was moved into the output dir after a successful test
    assert (output_dir / WHEEL_NAME).exists()


def test_run_host_build_build_only(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    backend = FakeBackend([FakeConfig(IDENTIFIER)], tmp_path / WHEEL_NAME)

    run_host_build(backend, _options(output_dir), tmp_path, stages=frozenset({Stage.BUILD}))

    # the wheel is built and moved, but tests are skipped
    assert "build_wheel" in backend.calls
    assert not any(isinstance(c, tuple) for c in backend.calls)
    assert (output_dir / WHEEL_NAME).exists()


def test_run_host_build_test_only(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    # a wheel built by an earlier run
    (output_dir / WHEEL_NAME).write_bytes(b"")
    backend = FakeBackend([FakeConfig(IDENTIFIER)], tmp_path / WHEEL_NAME)

    run_host_build(backend, _options(output_dir), tmp_path, stages=frozenset({Stage.TEST}))

    assert backend.calls == [
        "setup",
        ("test_wheel", WHEEL_NAME),
        "teardown",
    ]
    # nothing built, so the pre-existing wheel is left in place
    assert (output_dir / WHEEL_NAME).exists()


def test_run_host_build_test_only_missing_wheel(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    backend = FakeBackend([FakeConfig(IDENTIFIER)], tmp_path / WHEEL_NAME)

    with pytest.raises(errors.FatalError, match="No pre-built wheel"):
        run_host_build(backend, _options(output_dir), tmp_path, stages=frozenset({Stage.TEST}))
