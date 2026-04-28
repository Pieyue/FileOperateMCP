import sqlite3
import json
import csv
import uuid
import aiofiles
from pathlib import Path
from datetime import datetime
from functools import wraps

BASE_PATH = Path('Data')
RECOVERY_PATH = Path("Recovery")
BASE_PATH.mkdir(exist_ok=True, parents=True)
RECOVERY_PATH.mkdir(exist_ok=True, parents=True)

# 日志文件使用绝对路径
LOG_FILE = Path(__file__).parent / 'record.csv'


def parse_line_range(line_spec: str, total_lines: int) -> list[int]:
    """
    解析行范围字符串，返回需要读取的行号列表（从1开始）

    格式示例：
    - "5": 第5行
    - "-5": 倒数5行
    - "2-10": 第2到10行
    - "2,6,4": 第2、6、4行
    - "2-5 11,12": 第2-5行和第11、12行
    - "1-3 5,9": 第1-3行和第5、9行

    :param line_spec: 行范围字符串
    :param total_lines: 文件总行数
    :return: 需要读取的行号列表（已排序，从1开始）
    """
    if not line_spec or line_spec.strip() == '':
        return list(range(1, total_lines + 1))  # 默认全部

    result_lines = set()

    # 按空格分割成多个部分
    parts = line_spec.strip().split()

    for part in parts:
        # 检查是否包含逗号（多个单独行号）
        if ',' in part:
            # 处理逗号分隔的行号，如 "2,6,4"
            for item in part.split(','):
                item = item.strip()
                if not item:
                    continue
                try:
                    line_num = int(item)
                    # 处理负数（倒数）
                    if line_num < 0:
                        line_num = total_lines + line_num + 1
                    if 1 <= line_num <= total_lines:
                        result_lines.add(line_num)
                except ValueError:
                    raise ValueError(f"错误：无效的行号 '{item}'")

        # 检查是否包含连字符（范围）
        elif '-' in part and not part.startswith('-'):
            # 处理范围，如 "2-10"（排除负数情况）
            try:
                range_parts = part.split('-')
                if len(range_parts) != 2:
                    raise ValueError(f"错误：无效的范围格式 '{part}'")

                start = int(range_parts[0].strip())
                end = int(range_parts[1].strip())

                # 处理负数
                if start < 0:
                    start = total_lines + start + 1
                if end < 0:
                    end = total_lines + end + 1

                # 确保 start <= end
                if start > end:
                    start, end = end, start

                # 添加到结果集
                for i in range(start, end + 1):
                    if 1 <= i <= total_lines:
                        result_lines.add(i)
            except ValueError as e:
                if "无效的行号" in str(e) or "无效的范围" in str(e):
                    raise
                raise ValueError(f"错误：无效的范围格式 '{part}'")

        else:
            # 单个数字，如 "5" 或 "-5"
            try:
                line_num = int(part)

                if line_num > 0:
                    # 正数：指定行号（不是前N行）
                    if 1 <= line_num <= total_lines:
                        result_lines.add(line_num)
                elif line_num < 0:
                    # 负数：倒数N行
                    start_line = total_lines + line_num + 1  # 例如 -5 表示从第16行开始（20-5+1）
                    if start_line < 1:
                        start_line = 1
                    for i in range(start_line, total_lines + 1):
                        result_lines.add(i)
                else:
                    raise ValueError("错误：行号不能为0")
            except ValueError as e:
                if "行号不能为0" in str(e):
                    raise
                raise ValueError(f"错误：无效的行号 '{part}'")

    # 返回排序后的列表
    return sorted(result_lines)

def generate_recovery_id() -> str:
    """
    生成回收站文件的唯一 ID
    使用 UUID4 的前 20 位，几乎零碰撞概率，无需检查重复
    :return: 20位唯一标识符
    """
    return str(uuid.uuid4())

def safe_path(path: str) -> Path|bool:
    # resolve() 绝对路径 + 规范化 + 解析符号链接 + 判断路径是否存在
    full_path = (BASE_PATH / path).resolve()
    try:
        full_path.relative_to(BASE_PATH.resolve())
        return full_path
    except ValueError:
        return False

def move_copy_check(src_path, dst_path, override=False):
    if not src_path.exists():
        raise FileNotFoundError(f"错误：{str(src_path)} 不存在")
    if dst_path.is_dir() and not (dst_path.exists()):
        raise FileNotFoundError(f"错误：{str(dst_path)} 不存在，请先创建目录")
    if dst_path.is_file():
        if not (dst_path.parent.exists()):
            raise FileNotFoundError(f"错误：{str(dst_path.parent)} 不存在，请先创建目录")
        if dst_path.exists() and override is False:
            raise FileExistsError(f"错误：{str(dst_path)} 目录中存在同名文件，请重命名要复制的文件或删除同名文件，或将override设为True")

def initial_db():
    """ 初始化数据库 """
    with sqlite3.connect('mcp.db') as conn:
        cursor = conn.cursor()
        tables = cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tb_exist = False
        for table in tables:
            if 'recovery' in table:
                tb_exist = True
                break
        if not tb_exist:
            sql = """
                  CREATE TABLE recovery \
                  ( \
                      id       char(20)      NOT NULL PRIMARY KEY UNIQUE, \
                      ori_path     varchar(1024) NOT NULL, \
                      datetime DATETIME
                  ) \
                  """
            cursor.execute(sql)

def logger(func):
    """
    日志装饰器：记录函数调用的参数、结果和异常
    使用 CSV 格式安全地记录日志，避免特殊字符导致的格式问题
    支持异步函数
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        func_name = func.__name__
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 将 args 和 kwargs 序列化为 JSON 字符串，避免 CSV 格式混乱
        args_str = json.dumps(args, ensure_ascii=False, default=str)
        kwargs_str = json.dumps(kwargs, ensure_ascii=False, default=str)
        
        try:
            result = await func(*args, **kwargs)
            # 成功时记录日志，使用utf-8-sig编码，以防乱码
            async with aiofiles.open(LOG_FILE, 'a', encoding='utf-8-sig', newline='') as log:
                await log.write(','.join([func_name, args_str, kwargs_str, 'Success', timestamp, '']) + '\n')
            return result
        except Exception as e:
            # 失败时记录日志，包含错误信息
            error_msg = str(e).replace('\n', ' | ')  # 替换换行符，保持单行
            async with aiofiles.open(LOG_FILE, 'a', encoding='utf-8-sig', newline='') as log:
                await log.write(','.join([func_name, args_str, kwargs_str, 'Fail', timestamp, error_msg]) + '\n')
            raise
    return wrapper