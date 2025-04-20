import asyncio
import json
import os

import pytest
from pydantic import BaseModel

from sekaibot.config import ConfigModel
from sekaibot.utils.bot import (
    PydanticEncoder,
    cancel_on_exit,
    flatten_exception_group,
    flatten_tree_with_jumps,
    is_config_class,
    remove_none_attributes,
    run_coro_with_catch,
    samefile,
    sync_func_wrapper,
    wrap_get_func,
)


@pytest.fixture
def sample_config_class():
    class MyConfig(ConfigModel):
        __config_name__ = "my"
        foo: int = 1

    return MyConfig


def test_is_config_class(sample_config_class):
    MyConfig = sample_config_class
    assert is_config_class(MyConfig)

    # Not a subclass of ConfigModel
    class NotConfig(BaseModel):
        pass

    assert not is_config_class(NotConfig)


def test_remove_none_attributes():
    class M(ConfigModel):
        a: int = 1
        b: int | None = None
        c: int | None = None

    m = M()
    m.b = 2
    m.c = None
    cleaned = remove_none_attributes(m, exclude={"c"})
    assert hasattr(cleaned, "a")
    assert hasattr(cleaned, "b")
    # c should still exist due to exclude
    assert hasattr(cleaned, "c")


def test_flatten_tree_with_jumps():
    class A:
        pass

    class B:
        pass

    class C:
        pass

    class D:
        pass

    # A has children B and D; B has child C
    tree = {A: {B: {C: {}}, D: {}}}
    flat = flatten_tree_with_jumps(tree)
    nodes = [n for n, _ in flat]
    assert set(nodes) == {A, B, C, D}


def test_flatten_exception_group():
    from exceptiongroup import ExceptionGroup

    eg = ExceptionGroup("grp", [ValueError("v"), ExceptionGroup("sub", [TypeError("t")])])
    flat = list(flatten_exception_group(eg))
    assert any(isinstance(e, ValueError) for e in flat)
    assert any(isinstance(e, TypeError) for e in flat)


@pytest.mark.anyio
async def test_run_coro_with_catch():
    async def good():
        return "ok"

    async def bad():
        raise KeyError("err")

    res1 = await run_coro_with_catch(good(), (KeyError,), return_on_err=None)
    assert res1 == "ok"
    res2 = await run_coro_with_catch(bad(), (KeyError,), return_on_err="fallback")
    assert res2 == "fallback"


def test_pydantic_encoder():
    class M(BaseModel):
        x: int

    m = M(x=5)
    js = json.dumps({"m": m}, cls=PydanticEncoder)
    assert '"x": 5' in js


def test_samefile(tmp_path):
    f1 = tmp_path / "a.txt"
    f2 = tmp_path / "b.txt"
    f1.write_text("test")
    os.link(f1, f2)
    assert samefile(str(f1), str(f2))
    # nonexistent file
    assert not samefile(str(f1), str(tmp_path / "c.txt"))


def test_sync_func_wrapper_and_wrap_get_func():
    def sync_fn(x):
        return x + 1

    async_fn = sync_func_wrapper(sync_fn)
    result = asyncio.get_event_loop().run_until_complete(async_fn(4))
    assert result == 5
    # wrap_get_func returns coroutine
    func = wrap_get_func(lambda e: True)

    class E:
        pass

    coro = func(E())
    assert asyncio.get_event_loop().run_until_complete(coro)


@pytest.mark.anyio
async def test_cancel_on_exit():
    import anyio

    ev = anyio.Event()
    scope = anyio.create_cancel_scope()

    async def setter():
        await asyncio.sleep(0.01)
        ev.set()

    async with anyio.create_task_group() as tg:
        tg.start_soon(cancel_on_exit, ev, scope)
        tg.start_soon(setter)
    assert scope.cancel_called
