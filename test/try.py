from typing import Any, Callable, Type, Awaitable, AsyncGenerator, Generator, AsyncContextManager, ContextManager, Union, TypeVar
_T = TypeVar("_T")
# 依赖类型
Dependency = Union[
    # Class-based dependencies
    Type[Union[_T, AsyncContextManager[_T], ContextManager[_T]]],
    # Generator-based dependencies
    Callable[[], AsyncGenerator[_T, None]],
    Callable[[], Generator[_T, None, None]],
    # Function-based dependencies (带参数)
    Callable[..., _T],
    Callable[..., Awaitable[_T]],
]

def get_dependency_name(dependency: Dependency[Any]) -> str:
    """获取 Dependency[Any] 的名称，正确区分类、函数、实例等"""

    if isinstance(dependency, type):
        return dependency.__name__
    if callable(dependency):
        if hasattr(dependency, "__name__"):
            return dependency.__name__ if dependency.__name__ != "<lambda>" else "lambda"
        return dependency.__class__.__name__
    return dependency.__class__.__name__

# ✅ 测试
class MyClass:
    pass

async def async_func():
    pass

def sync_func():
    pass

class CallableClass:
    def __call__(self):
        pass

print(get_dependency_name(MyClass))  # MyClass (类本身)
print(get_dependency_name(MyClass()))  # MyClass (类实例)
print(get_dependency_name(sync_func))  # sync_func (普通函数)
print(get_dependency_name(async_func))  # async_func (异步函数)
print(get_dependency_name(lambda x: x))  # lambda (匿名函数)
print(get_dependency_name(CallableClass()))  # CallableClass (可调用类)
