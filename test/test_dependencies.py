from collections.abc import AsyncGenerator, Generator
from contextlib import AsyncExitStack
from types import TracebackType
from typing import Self

import pytest
from pytest_mock import MockerFixture

from sekaibot.dependencies import Depends, solve_dependencies


def test_repr_inner_depends() -> None:
    from sekaibot import Bot

    assert repr(Depends()) == "InnerDepends(NoneType)"
    assert repr(Depends(use_cache=False)) == "InnerDepends(NoneType, use_cache=False)"
    assert repr(Depends(Bot)) == "InnerDepends(Bot)"


@pytest.mark.anyio
async def test_depends() -> None:
    class DepA: ...

    class DepB: ...

    class Dependent:
        a: DepA = Depends()
        b: DepB = Depends()

    obj = None

    async with AsyncExitStack() as stack:
        obj = await solve_dependencies(
            Dependent,
            use_cache=True,
            stack=stack,
            dependency_cache={},
        )

    assert obj is not None
    assert isinstance(obj.a, DepA)
    assert isinstance(obj.b, DepB)


@pytest.mark.anyio
async def test_sub_depends() -> None:
    class DepA: ...

    class DepB:
        a: DepA = Depends()

    class Dependent:
        a: DepA = Depends()
        b: DepB = Depends()

    obj = None

    async with AsyncExitStack() as stack:
        obj = await solve_dependencies(
            Dependent,
            use_cache=True,
            stack=stack,
            dependency_cache={},
        )

    assert obj is not None
    assert isinstance(obj.a, DepA)
    assert isinstance(obj.b, DepB)
    assert obj.b.a is obj.a


@pytest.mark.anyio
async def test_depends_context_manager(mocker: MockerFixture) -> None:
    class DepA:
        def __enter__(self) -> Self:
            return self

        def __exit__(
            self,
            _exc_type: type[BaseException] | None,
            _exc_value: BaseException | None,
            _traceback: TracebackType | None,
        ) -> None:
            pass

    class DepB:
        a: DepA = Depends()

    class Dependent:
        a: DepA = Depends()
        b: DepB = Depends()

    enter_spy = mocker.spy(DepA, "__enter__")
    exit_spy = mocker.spy(DepA, "__exit__")

    obj = None

    async with AsyncExitStack() as stack:
        obj = await solve_dependencies(
            Dependent,
            use_cache=True,
            stack=stack,
            dependency_cache={},
        )

    assert obj is not None
    assert isinstance(obj.a, DepA)
    assert isinstance(obj.b, DepB)
    assert obj.b.a is obj.a
    enter_spy.assert_called_once()
    exit_spy.assert_called_once()


@pytest.mark.anyio
async def test_depends_async_context_manager(mocker: MockerFixture) -> None:
    class DepA:
        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(
            self,
            _exc_type: type[BaseException] | None,
            _exc_value: BaseException | None,
            _traceback: TracebackType | None,
        ) -> None:
            pass

    class DepB:
        a: DepA = Depends()

    class Dependent:
        a: DepA = Depends()
        b: DepB = Depends()

    aenter_spy = mocker.spy(DepA, "__aenter__")
    aexit_spy = mocker.spy(DepA, "__aexit__")

    obj = None

    async with AsyncExitStack() as stack:
        obj = await solve_dependencies(
            Dependent,
            use_cache=True,
            stack=stack,
            dependency_cache={},
        )

    assert obj is not None
    assert isinstance(obj.a, DepA)
    assert isinstance(obj.b, DepB)
    assert obj.b.a is obj.a
    aenter_spy.assert_called_once()
    aexit_spy.assert_called_once()


@pytest.mark.anyio
async def test_depends_generator(mocker: MockerFixture) -> None:
    mock = mocker.MagicMock()

    class DepA: ...

    def dep_a() -> Generator[DepA, None, None]:
        mock("enter")
        yield DepA()
        mock("exit")

    class DepB:
        a = Depends(dep_a)

    class Dependent:
        a = Depends(dep_a)
        b: DepB = Depends()

    obj = None

    async with AsyncExitStack() as stack:
        obj = await solve_dependencies(
            Dependent,
            use_cache=True,
            stack=stack,
            dependency_cache={},
        )

    assert obj is not None
    assert isinstance(obj.a, DepA)
    assert isinstance(obj.b, DepB)
    assert obj.b.a is obj.a
    assert mock.call_args_list == [mocker.call("enter"), mocker.call("exit")]


@pytest.mark.anyio
async def test_depends_async_generator(mocker: MockerFixture) -> None:
    mock = mocker.AsyncMock()

    class DepA: ...

    async def dep_a() -> AsyncGenerator[DepA, None]:
        await mock("enter")
        yield DepA()
        await mock("exit")

    class DepB:
        a = Depends(dep_a)

    class Dependent:
        a = Depends(dep_a)
        b: DepB = Depends()

    obj = None

    async with AsyncExitStack() as stack:
        obj = await solve_dependencies(
            Dependent,
            use_cache=True,
            stack=stack,
            dependency_cache={},
        )

    assert obj is not None
    assert isinstance(obj.a, DepA)
    assert isinstance(obj.b, DepB)
    assert obj.b.a is obj.a
    assert mock.call_args_list == [mocker.call("enter"), mocker.call("exit")]


@pytest.mark.anyio
async def test_depends_solve_error() -> None:
    class Dependent:
        a = Depends()  # type: ignore

    with pytest.raises(TypeError):
        async with AsyncExitStack() as stack:
            await solve_dependencies(
                Dependent,
                use_cache=True,
                stack=stack,
                dependency_cache={},
            )


@pytest.mark.anyio
async def test_depends_type_error() -> None:
    class Dependent:
        a = Depends(1)  # type: ignore

    with pytest.raises(TypeError):
        async with AsyncExitStack() as stack:
            await solve_dependencies(
                Dependent,
                use_cache=True,
                stack=stack,
                dependency_cache={},
            )


@pytest.mark.anyio
async def test_function_dependency(mocker: MockerFixture) -> None:
    mock = mocker.MagicMock()

    class DepA: ...

    def create_dep_a() -> DepA:
        mock("created")
        return DepA()

    class Dependent:
        a = Depends(create_dep_a)

    obj = None

    async with AsyncExitStack() as stack:
        obj = await solve_dependencies(
            Dependent,
            use_cache=False,
            stack=stack,
            dependency_cache={},
        )

    assert obj is not None
    assert isinstance(obj.a, DepA)
    mock.assert_called_once_with("created")


@pytest.mark.anyio
async def test_async_function_dependency(mocker: MockerFixture) -> None:
    mock = mocker.MagicMock()

    class DepA: ...

    async def create_dep_a() -> DepA:
        mock("async_created")
        return DepA()

    class Dependent:
        a = Depends(create_dep_a)

    obj = None

    async with AsyncExitStack() as stack:
        obj = await solve_dependencies(
            Dependent,
            use_cache=False,
            stack=stack,
            dependency_cache={},
        )

    assert obj is not None
    assert isinstance(obj.a, DepA)
    mock.assert_called_once_with("async_created")


@pytest.mark.anyio
async def test_function_with_parameters(mocker: MockerFixture) -> None:
    mock = mocker.MagicMock()

    class DepA: ...

    class DepB: ...

    def create_dep(a: DepA) -> DepB:  # 测试函数参数依赖注入
        mock("called_with", a)
        return DepB()

    class Dependent:
        a = Depends()
        b = Depends(create_dep)

    obj = None

    async with AsyncExitStack() as stack:
        obj = await solve_dependencies(
            Dependent,
            use_cache=True,
            stack=stack,
            dependency_cache={},
        )

    assert obj is not None
    assert isinstance(obj.a, DepA)
    assert isinstance(obj.b, DepB)
    mock.assert_called_once_with("called_with", obj.a)


@pytest.mark.anyio
async def test_function_parameter_injection(mocker: MockerFixture) -> None:
    mock = mocker.MagicMock()

    class DepA: ...

    class DepB: ...

    class DepC: ...

    def create_dep(a: DepA, b: DepB) -> DepC:
        mock("create_dep_called", a, b)
        return DepC()

    class Dependent:
        a = Depends()
        b = Depends()
        c = Depends(create_dep)

    obj = None

    async with AsyncExitStack() as stack:
        obj = await solve_dependencies(
            Dependent,
            use_cache=True,
            stack=stack,
            dependency_cache={},
        )

    assert obj is not None
    assert isinstance(obj.a, DepA)
    assert isinstance(obj.b, DepB)
    assert isinstance(obj.c, DepC)
    mock.assert_called_once_with("create_dep_called", obj.a, obj.b)


@pytest.mark.anyio
async def test_mixed_dependency_types(mocker: MockerFixture) -> None:
    mock = mocker.MagicMock()

    class DepA: ...

    class DepB: ...

    def create_b(a: DepA) -> DepB:
        mock("b_created", a)
        return DepB()

    class DepC: ...

    async def create_c(b: DepB) -> DepC:
        mock("c_created", b)
        return DepC()

    class Dependent:
        a = Depends()
        b = Depends(create_b)
        c = Depends(create_c)

    obj = None

    async with AsyncExitStack() as stack:
        obj = await solve_dependencies(
            Dependent,
            use_cache=True,
            stack=stack,
            dependency_cache={},
        )

    assert obj is not None
    assert isinstance(obj.a, DepA)
    assert isinstance(obj.b, DepB)
    assert isinstance(obj.c, DepC)
    assert mock.call_args_list == [
        mocker.call("b_created", obj.a),
        mocker.call("c_created", obj.b),
    ]


@pytest.mark.anyio
async def test_dependency_cache_behavior(mocker: MockerFixture) -> None:
    mock = mocker.MagicMock()

    class DepA: ...

    def create_a() -> DepA:
        mock("a_created")
        return DepA()

    class DepB: ...

    def create_b(a: DepA = Depends(create_a)) -> DepB:  # 显式使用缓存  # noqa: B008
        mock("b_created")
        return DepB()

    class Dependent:
        a = Depends(create_a)
        b = Depends(create_b)

    obj = None

    async with AsyncExitStack() as stack:
        obj = await solve_dependencies(
            Dependent,
            use_cache=True,
            stack=stack,
            dependency_cache={},
        )

    assert obj is not None
    assert obj.b.a is obj.a  # 验证缓存实例被复用
    assert mock.call_args_list == [mocker.call("a_created"), mocker.call("b_created")]
