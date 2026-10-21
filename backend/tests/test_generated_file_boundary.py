"""真实子进程写入/恢复与链接反例；不调用Provider。"""

import hashlib

import pytest
from pydantic import ValidationError

from deerflow.compile.generated_file_boundary import FileBoundary, GenerationRule, file_hashes, guard_main, guarded_command, original_command


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.fixture
def fixture(tmp_path):
    for name, value in {"main.c": "author", "test.sh": "test", "configure.ac": "input", "config.h.in": "old"}.items():
        (tmp_path / name).write_text(value)
    command = "printf generated > config.h.in"
    p = FileBoundary(
        baseline=file_hashes(tmp_path),
        protected_inputs=("main.c", "test.sh", "configure.ac"),
        generations=(GenerationRule(command=command, workdir="/workspace/repo", inputs=("configure.ac",), outputs={"config.h.in": sha("generated")}, evidence="人工标准生成关系夹具"),),
        new_files=("config.h.in~",),
        new_directories=("build",),
    )
    return tmp_path, p, command


def execute(fixture, command, *, declared=False):
    root, policy, _ = fixture
    payload = policy.model_dump(mode="json")
    if declared:
        payload["generations"][0]["workdir"] = str(root)
    return guard_main(payload, command, str(root), str(root))


def test_declared_generation_and_normal_build_output(fixture):
    assert execute(fixture, fixture[2], declared=True) == 0
    assert execute(fixture, "mkdir build && printf object > build/main.o") == 0


@pytest.mark.parametrize("name", ["main.c", "test.sh", "configure.ac"])
def test_modified_and_restored_originals_are_rejected(fixture, name):
    command = f"cp {name} build-copy; printf tamper > {name}; cat build-copy > {name}; rm build-copy"
    with pytest.raises(ValueError, match="保护文件"):
        execute(fixture, command)


def test_generated_output_cannot_be_manually_written_even_to_expected_hash(fixture):
    with pytest.raises(ValueError, match="非声明命令"):
        execute(fixture, "printf generated > config.h.in; :")


def test_generator_wrong_output_rejected(fixture):
    root, policy, command = fixture
    payload = policy.model_dump(mode="json")
    payload["generations"][0].update(command="printf wrong > config.h.in", workdir=str(root))
    with pytest.raises(ValueError, match="标准生成结果"):
        guard_main(payload, "printf wrong > config.h.in", str(root), str(root))


@pytest.mark.parametrize("command", ["mv main.c saved; printf bad > main.c; rm main.c; mv saved main.c", "mkdir alt; mv main.c alt/main.c; mv alt/main.c main.c; rmdir alt"])
def test_replacement_and_restoration_are_rejected(fixture, command):
    with pytest.raises(ValueError, match="保护文件"):
        execute(fixture, command)


def test_undeclared_new_source_rejected(fixture):
    with pytest.raises(ValueError, match="未声明的新文件"):
        execute(fixture, "printf new > injected.c")


def test_outside_link_rejected_without_reading_target(fixture):
    with pytest.raises(ValueError, match="链接"):
        execute(fixture, "mkdir build; ln -s /etc/passwd build/alias")


def test_nonzero_original_exit_is_not_hidden(fixture):
    assert execute(fixture, "exit 17") == 17


def test_output_directory_cannot_hide_new_source(fixture):
    with pytest.raises(ValueError, match="隐式授予源码"):
        execute(fixture, "mkdir build; printf fake > build/replacement.c")


def test_restored_parent_directory_move_is_rejected(fixture):
    root, policy, _ = fixture
    (root / "src").mkdir()
    (root / "src/author.c").write_text("author")
    payload = policy.model_dump(mode="json")
    payload["baseline"]["src/author.c"] = sha("author")
    with pytest.raises(ValueError, match="祖先目录"):
        guard_main(payload, "mv src temp-src; mv temp-src src", str(root), str(root))


def test_generator_permission_does_not_allow_modifying_its_input(fixture):
    root, policy, _ = fixture
    payload = policy.model_dump(mode="json")
    command = "cp configure.ac config.h.in~; printf bad > configure.ac; cat config.h.in~ > configure.ac; printf generated > config.h.in"
    payload["generations"][0].update(command=command, workdir=str(root))
    with pytest.raises(ValueError, match="保护文件"):
        guard_main(payload, command, str(root), str(root))


def test_guard_roundtrip_is_bound_to_exact_policy(fixture):
    _, policy, command = fixture
    wrapped = guarded_command(policy, command, "/workspace/repo")
    assert original_command(policy, wrapped) == command
    other = policy.model_copy(update={"new_files": ()})
    with pytest.raises(Exception, match="任务身份"):
        original_command(other, wrapped)


@pytest.mark.parametrize("change", [{"protected_inputs": ("config.h.in",)}, {"new_directories": (".",)}, {"new_directories": ("main.c",)}, {"new_files": ("../x",)}, {"new_files": ("*.c",)}])
def test_invalid_or_overlapping_output_permissions_rejected(fixture, change):
    with pytest.raises(ValidationError):
        FileBoundary.model_validate({**fixture[1].model_dump(), **change})
