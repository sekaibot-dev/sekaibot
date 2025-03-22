import os
import libcst as cst


class ReplaceUnionOptional(cst.CSTTransformer):
    def leave_Subscript(self, original_node: cst.Subscript, updated_node: cst.Subscript):
        """转换 Union 和 Optional 语法"""
        if isinstance(original_node.value, cst.Name):
            type_name = original_node.value.value
            if type_name in {"Union", "Optional"}:
                # 获取 Union 或 Optional 内的类型
                if isinstance(original_node.slice, cst.Tuple):
                    inner_types = [e.value for e in original_node.slice.elements]
                else:
                    inner_types = [original_node.slice.value]

                # Optional[T] -> T | None
                if type_name == "Optional":
                    inner_types.append(cst.Name("None"))

                # 多个元素使用 | 连接
                result = inner_types[0]
                for t in inner_types[1:]:
                    result = cst.BinaryOperation(left=result, operator=cst.BitOr(), right=t)
                return result
        return updated_node


def convert_code(source_code: str) -> str:
    """转换 Python 代码，将 Union / Optional 替换为 | 语法"""
    tree = cst.parse_module(source_code)
    new_tree = tree.visit(ReplaceUnionOptional())
    return new_tree.code


def convert_directory(directory: str):
    """遍历指定目录，转换所有 Python 文件"""
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                print(f"Processing: {file_path}")

                # 读取原文件
                with open(file_path, "r", encoding="utf-8") as f:
                    old_code = f.read()

                # 转换代码
                new_code = convert_code(old_code)

                # 覆盖原文件
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(new_code)

                print(f"✅ Converted: {file_path}")


# 指定要转换的目录
directory_path = "./sekaibot"  # ⚠️ 替换为你的 Python 代码目录路径
convert_directory(directory_path)
