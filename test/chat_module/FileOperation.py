import json
import os  # 用于检查文件是否存在
import queue
import threading

import chardet  # 用于检测文件编码
import toml  # type: ignore

# 队列来保存读写任务
task_queue = queue.Queue()
# 用于存储读取结果的队列
result_queue = queue.Queue()

# 创建文件锁
file_lock = threading.Lock()


def detect_encoding(file_path, default_encoding="utf-8"):
    # 尝试使用 chardet 来检测文件编码
    try:
        with open(file_path, "rb") as f:
            raw_data = f.read(1024)  # 读取部分数据用于检测编码
            result = chardet.detect(raw_data)
            encoding = result["encoding"]
            if encoding:
                return encoding
    except FileNotFoundError:
        pass

    # 如果无法检测或出错，返回默认编码
    return default_encoding


def create_empty_file(file_path, file_type, encoding="utf-8"):
    with open(file_path, "w", encoding=encoding) as file:
        if file_type == "json":
            json.dump({}, file, indent=4)
        elif file_type == "toml":
            toml.dump({}, file)


def read_file(file_path, file_type, encoding="utf-8"):
    with open(file_path, encoding=encoding) as file:
        if file_type == "json":
            return json.load(file)
        elif file_type == "toml":
            return toml.load(file)


def write_file(file_path, data, file_type, encoding="utf-8"):
    with open(file_path, "r+", encoding=encoding) as file:
        try:
            if file_type == "json":
                file_data = json.load(file)
            elif file_type == "toml":
                file_data = toml.load(file)
        except (json.JSONDecodeError, toml.TomlDecodeError):  # 文件为空或损坏
            file_data = {}

        # 合并原始数据和新数据
        if isinstance(file_data, dict) and isinstance(data, dict):
            file_data.update(data)
        else:
            file_data = data

        file.seek(0)  # 文件指针回到文件开头
        if file_type == "json":
            json.dump(file_data, file, indent=4)
        elif file_type == "toml":
            toml.dump(file_data, file)
        file.truncate()  # 截断文件内容，确保只写入新数据


def detect_file_type(file_path):
    if file_path.endswith(".json"):
        return "json"
    elif file_path.endswith(".toml"):
        return "toml"
    else:
        raise ValueError(f"Unsupported file type for file: {file_path}")


def worker():
    while True:
        task = task_queue.get()
        if task is None:  # Sentinel to stop the worker
            break

        # 处理读写任务
        action, data, file_path, result_queue = task

        with file_lock:  # 确保线程安全
            file_type = detect_file_type(file_path)
            encoding = detect_encoding(file_path)

            if action == "write":
                # 如果文件不存在，自动创建文件
                if not os.path.exists(file_path):
                    create_empty_file(file_path, file_type, encoding=encoding)

                try:
                    write_file(file_path, data, file_type, encoding=encoding)
                except FileNotFoundError:
                    print(f"File {file_path} not found!")
                except PermissionError:
                    print(f"Permission denied for file {file_path}!")

            elif action == "read":
                # 如果文件不存在，创建文件并返回空字典
                if not os.path.exists(file_path):
                    create_empty_file(file_path, file_type, encoding=encoding)
                    result_queue.put({})  # 如果文件不存在，返回空字典

                try:
                    file_data = read_file(file_path, file_type, encoding=encoding)
                    result_queue.put(file_data)  # 将读取的数据放入结果队列
                except (FileNotFoundError, json.JSONDecodeError, toml.TomlDecodeError):
                    print(f"Error reading {file_path}: File is empty or corrupted.")
                    result_queue.put(None)  # 读取失败时放入None
                except PermissionError:
                    print(f"Permission denied for file {file_path}!")
                    result_queue.put(None)

        task_queue.task_done()  # 标记任务完成


# 启动后台线程
worker_thread = threading.Thread(target=worker, daemon=True)
worker_thread.start()


# 读写请求函数
def add_write_task(data_to_write, file_path):
    task_queue.put(("write", data_to_write, file_path, None))


def add_read_task(file_path):
    task_queue.put(("read", None, file_path, result_queue))
    # 等待读取结果并返回
    return result_queue.get()


# 停止工作线程
def stop_worker():
    task_queue.put(None)
    worker_thread.join()


# 使用示例
if __name__ == "__main__":
    task_queue.put(None)
    worker_thread.join()  # 确保所有任务处理完毕后再退出
