"""
Author: Pieyue
"""

import os
import shutil
import re
import base64
import sqlite3
from pathlib import Path
from datetime import datetime
from fastmcp import FastMCP
from utils import (safe_path, move_copy_check, initial_db, logger, generate_recovery_id, parse_line_range,
                   BASE_PATH, RECOVERY_PATH, LOG_FILE)

initial_db()

if not LOG_FILE.exists():
    LOG_FILE.write_text("func_name,args_str,kwargs_str,status,timestamp,error_msg", encoding="utf-8-sig")

mcp = FastMCP()

@mcp.tool()
@logger
def read_file_content(user_path: str, mode:str='text', encoding:str='utf-8', lines:str='', bytes_count:int|None=None) -> str:
    """
    根据路径读取文件
    :param user_path: 相对于基础目录的文件地址。注：不允许使用'..'等方式跳到基础目录外
    :param mode: 读取方式，text：读取文本，binary：以二进制形式读取（返回Base64编码），默认为text
    :param encoding: 编码方式，默认utf-8（仅在mode=text时有效）
    :param lines: 行范围表达式（仅mode=text时有效），支持：
                  ''（空字符串）：读取全部行（默认）
                  '5'：第5行
                  '-1'：倒数第1行
                  '-5'：倒数5行
                  '2-10'：第2到10行
                  '2,6,4'：第2、6、4行
                  '2-5 11,12'：第2-5行和第11、12行
    :param bytes_count: 读取的字节数（仅mode=binary时有效）：
                  None：读取全部字节（默认）
                  正整数：读取前N个字节
                  负整数：读取倒数N个字节（-1表示倒数1字节）
    :return: 文件的文本内容或Base64编码的二进制数据。如果发生错误，则返回错误信息字符串
    """
    try:
        path = safe_path(user_path)
        if path:
            if not path.exists():
                raise FileNotFoundError(f"错误：文件{user_path}不存在")
            
            if mode == 'text':
                # 首先读取所有行
                with open(path, 'r', encoding=encoding) as f:
                    all_lines = f.readlines()
                
                total_lines = len(all_lines)
                
                # 解析行范围
                if lines.strip() == '':
                    # 空字符串：读取全部
                    return ''.join(all_lines)
                else:
                    # 解析行范围表达式
                    target_line_nums = parse_line_range(lines, total_lines)
                    
                    # 提取指定的行（行号从1开始，列表索引从0开始）
                    result_lines = []
                    for line_num in target_line_nums:
                        if 1 <= line_num <= total_lines:
                            result_lines.append(all_lines[line_num - 1])
                    
                    return ''.join(result_lines)
            
            elif mode == 'binary':
                # 二进制模式读取
                file_size = path.stat().st_size  # 获取文件大小
                
                if bytes_count is None:
                    # 默认：读取全部字节
                    binary_data = path.read_bytes()
                elif bytes_count > 0:
                    # 读取前N个字节
                    with open(path, 'rb') as f:
                        binary_data = f.read(bytes_count)
                elif bytes_count < 0:
                    # 读取倒数N个字节
                    abs_count = abs(bytes_count)
                    if abs_count >= file_size:
                        # 如果请求的字节数大于等于文件大小，读取全部
                        binary_data = path.read_bytes()
                    else:
                        # 从文件末尾向前读取N个字节
                        with open(path, 'rb') as f:
                            # 2：步长，参照点 文件末尾
                            f.seek(-abs_count, 2)  # 从文件末尾向前偏移
                            binary_data = f.read()
                else:
                    raise ValueError(f"错误：bytes_count参数不能为0")
                
                # 转换为 Base64 编码
                base64_str = base64.b64encode(binary_data).decode('ascii')
                return base64_str
            
            else:
                raise ValueError(f"错误：不支持的读取模式 '{mode}'，请使用 text/binary")

        raise PermissionError("错误：非法路径，你只能在基础目录内读写文件")
    except Exception as e:
        raise Exception(f"服务器错误：{str(e)}")

@mcp.tool()
@logger
def find_str(user_path:str, regx:str, ignore_ul:bool=False, recursive:bool=True) -> str:
    """
    在文件中搜索匹配的文本
    :param user_path: 从基础目录开始的路径（文件或目录）。注：不可使用'..'跳到基础目录外
    :param regx: 正则表达式字符串，用于匹配文本
    :param ignore_ul: 是否忽略大小写，默认为False
    :param recursive: 是否递归搜索子目录，默认为True
    :return: 匹配结果字符串，格式为"文件路径(从基础路径开始):行号:匹配内容"，每行一个匹配。如果发生错误，返回错误信息
    """
    try:
        path = safe_path(user_path)
        if not path:
            raise PermissionError("错误：非法路径，你只能在基础目录内搜索")
        
        if not path.exists():
            raise FileNotFoundError(f"错误：路径{user_path}不存在")
        
        # 编译正则表达式（捕获异常防止恶意正则）
        try:
            flags = re.IGNORECASE if ignore_ul else 0
            pattern = re.compile(regx, flags)
        except re.error as e:
            raise ValueError(f"错误：无效的正则表达式 - {str(e)}")
        
        results = []
        
        def search_in_file(file_path: Path):
            """在单个文件中搜索"""
            try:
                # 尝试不同的编码读取文件
                for encoding in ['utf-8', 'gbk', 'latin-1']:
                    try:
                        with open(file_path, 'r', encoding=encoding, errors='ignore') as f:
                            for line_num, line in enumerate(f, 1):
                                if pattern.search(line):
                                    # 格式化输出：相对路径:行号:内容
                                    rel_path = str(file_path.relative_to(BASE_PATH))
                                    # 清理行尾换行符
                                    clean_line = line.rstrip('\n\r')
                                    results.append(f"{rel_path}:{line_num}:{clean_line}")
                        break  # 成功读取，跳出编码尝试循环
                    except UnicodeDecodeError:
                        continue  # 尝试下一个编码
            except Exception as e:
                # 跳过无法读取的文件（如二进制文件）
                pass
        
        if path.is_file():
            # 搜索单个文件
            search_in_file(path)
        elif path.is_dir():
            # 搜索目录
            if recursive:
                # path.rglob按名称递归列出所有子目录内的文件
                for file_path in path.rglob('*'):
                    if file_path.is_file():
                        search_in_file(file_path)
            else:
                # 仅搜索当前目录
                for file_path in path.glob('*'):
                    if file_path.is_file():
                        search_in_file(file_path)
        
        if results:
            return '\n'.join(results)
        else:
            return '未找到匹配的内容'
    except Exception as e:
        raise Exception(f"服务器错误：{str(e)}")


@mcp.tool()
@logger
def write_file_content(user_path:str, content:str='', mode:str='text', encoding:str='utf-8') -> str:
    """
    创建文件并向指定路径的文件写入内容
    :param user_path: 相对于基础目录的文件地址。注：不允许使用'..'等方式跳到基础目录外
    :param content: 要写入的内容（文本模式为字符串，二进制模式为Base64编码）
    :param mode: 写入模式，text(覆盖写入文本), append(追加文本), binary(覆盖写入二进制), append_binary(追加二进制)，默认为text
    :param encoding: 编码方式，默认utf-8（仅在文本模式有效）
    :return: 成功标志或错误信息
    """
    try:
        path = safe_path(user_path)
        if path:
            if not path.parent.exists():
                raise ValueError(f"错误：文件{user_path}所在目录不存在，请先创建目录！")
            
            if mode == 'text':
                # 文本覆盖写入
                length = path.write_text(content, encoding=encoding)
                return '文件创建成功' if length == 0 else '写入成功'
            
            elif mode == 'append':
                # 文本追加写入
                with open(path, 'a', encoding=encoding) as f:
                    f.write(content)
                return '追加成功'
            
            elif mode == 'binary':
                # 二进制覆盖写入（content为Base64编码）
                try:
                    binary_data = base64.b64decode(content)
                    path.write_bytes(binary_data)
                    return '二进制写入成功'
                except Exception as decode_error:
                    raise ValueError(f"错误：Base64解码失败 - {str(decode_error)}")
            
            elif mode == 'append_binary':
                # 二进制追加写入（content为Base64编码）
                try:
                    binary_data = base64.b64decode(content)
                    with open(path, 'ab') as f:
                        f.write(binary_data)
                    return '二进制追加成功'
                except Exception as decode_error:
                    raise ValueError(f"错误：Base64解码失败 - {str(decode_error)}")
            
            else:
                raise ValueError(f"错误：不支持的写入模式 '{mode}'，请使用 text/append/binary/append_binary")
        
        raise PermissionError("错误：非法路径，你只能在基础目录内读写文件")
    except Exception as e:
        raise Exception(f"服务器错误：{str(e)}")

@mcp.tool()
@logger
def move_file(src: str, dst: str, override:bool=False) -> str:
    """
    移动文件或目录，如果src与dst都在同一目录下，则执行重命名
    :param src: 从基础路径开始的待移动的文件(夹)的路径。注：不允许使用'..'等方式跳到基础目录外
    :param dst: 从基础路径开始的目标路径(要移动到哪里)。注：不允许使用'..'等方式跳到基础目录外
    :param override: 如果目标路径中存在同名文件(夹),是否覆盖(合并)？默认为False
    :return: 成功标志或错误信息
    """
    src_path, dst_path = safe_path(src), safe_path(dst)
    if not (src_path and dst_path):
        raise PermissionError("错误：非法路径，你只能在基础目录内操作")
    move_copy_check(src_path, dst_path, override)
    try:
        shutil.move(src_path, dst_path)
        return '移动成功' if src_path.parent == dst_path.parent else '重命名成功'
    except Exception as e:
        raise Exception(f"服务器错误：{str(e)}")

@mcp.tool()
@logger
def copy_file(src:str, dst: str, override:bool=False) -> str:
    """
    复制文件或目录
    :param src: 从基础路径开始的待复制的文件(夹)的路径。注：不允许使用'..'等方式跳到基础目录外
    :param dst: 从基础路径开始的目标路径(要复制到哪里)。注：不允许使用'..'等方式跳到基础目录外
    :param override: 如果目标路径中存在同名文件(夹),是否覆盖(合并)？默认为False
    :return: 成功标志或错误信息
    """
    src_path, dst_path = safe_path(src), safe_path(dst)
    if not (src_path and dst_path):
        raise PermissionError(r"错误：非法路径，你只能在基础目录内操作")
    move_copy_check(src_path, dst_path, override)

    try:
        if src_path.is_dir():
            shutil.copytree(src_path, dst_path)
            return '成功'
        elif src_path.is_file():
            shutil.copy(src_path, dst_path)
            return '成功'
        else:
            return '错误：对象非法'
    except Exception as e:
        raise Exception(f"服务器错误：{str(e)}")

@mcp.tool()
@logger
def delete_file(user_path:str) -> str:
    """
    删除文件或目录
    :param user_path: 从基础目录开始的待删除的文件(夹)的路径。注：不允许使用'..'等方式跳到基础目录外
    :return: id字符串，用于以后有需要时通过id字符串和recovery_file函数恢复文件(夹)
    """
    sql = """
    INSERT INTO recovery
        VALUES (?,?,?);
    """
    path = safe_path(user_path)
    if not path:
        raise PermissionError("错误：非法路径，你只能删除基础目录内的对象")
    if not path.exists():
        raise FileNotFoundError("错误：要删除的对象不存在")
    try:
        # 使用 UUID4 生成唯一 ID，几乎零碰撞概率，无需检查重复
        _id = generate_recovery_id()

        with sqlite3.connect('mcp.db') as conn:
            try:
                conn.cursor().execute(sql, (_id, str(path), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                conn.commit()
                RECOVERY_PATH.mkdir(exist_ok=True, parents=True)
                shutil.move(path, RECOVERY_PATH / _id)
            except Exception as e:
                conn.rollback()
                raise Exception(f"错误：{str(e)}")
        return f"成功！文件已删除，如果需要，你可以凭ID:{_id} 通过recovery_file恢复它们"
    except Exception as e:
        raise Exception(f"服务器错误：{str(e)}，文件未删除")

@mcp.tool()
@logger
def recovery_file(_id:str, override: bool=False) -> str:
    """
    通过删除文件时给出的ID，恢复对应的文件
    :param _id: 删除文件时返回的ID
    :param override: 如果恢复文件时遇到重名文件，是否覆盖。默认为False
    :return: 成功标志或错误信息
    """
    sql = """
    SELECT ori_path FROM recovery
        WHERE id = ?;
    """
    try:
        # 首先尝试从数据库获取原始路径
        with sqlite3.connect("mcp.db") as conn:
            cursor = conn.cursor()
            ori_path = cursor.execute(sql, (_id,)).fetchall()[0][0] # 传入元组，不然sqlite会将每一个字符当作一个参数
            if (not ori_path) or (not Path.exists(RECOVERY_PATH / _id)):
                # 如果回收站中不存在路径，或者数据库中没有ID，那么就清理数据库并返回错误信息
                cursor.execute("DELETE FROM recovery WHERE id=?", (_id,))
                conn.commit()
                raise FileNotFoundError("错误：回收站中没有这个文件，可能已被永久删除")
            # 获取后再尝试还原
            ori_path = Path(ori_path)
            if ori_path.exists() and override is False:
                raise FileExistsError("错误：要恢复的文件与现有文件重名，请先删除现有文件，或将override设为True")

            # 为了确保成功恢复，先检查一下父文件夹是否存在
            os.makedirs(str(ori_path.parent), exist_ok=True)
            shutil.move(RECOVERY_PATH / _id, ori_path)

            # 成功恢复后清理数据库
            cursor.execute("DELETE FROM recovery WHERE id=?", (_id,))
            conn.commit()
            return f"成功恢复文件到{str(ori_path).split(str(BASE_PATH))[-1]}"
    except Exception as e:
        raise Exception(f"服务器错误：{str(e)}，文件未恢复")

@mcp.tool()
@logger
def create_dir(user_path:str) -> str:
    """
    创建一个文件夹，如果是多级目录，会自动创建
    :param user_path: 从基础目录开始的路径。注：不可使用'..'跳到基础目录外
    :return: 成功标志或错误信息
    """
    try:
        path = safe_path(user_path)
        if path:
            Path.mkdir(path, parents=True)
            return "成功"
        else:
            raise PermissionError(f"错误：你只能在基础目录内创建文件夹")
    except Exception as e:
        raise Exception(f"服务器错误：{str(e)}")

@mcp.tool()
@logger
def list_dir(user_path:str='./') -> dict[str, str]|str:
    """
    列出目录中的所有对象
    :param user_path: 从基础目录开始的路径。注：不可使用'..'跳到基础目录外
    :return: 如果操作成功就返回一个包含当前目录内所有对象的字典，格式为{从基础目录开始的路径: 对象类型(f为文件，d为文件夹)}，否则返回错误信息
    """
    res = {}
    try:
        path = safe_path(user_path)
        if path:
            if path.exists():
                for obj in os.listdir(str(path)):
                    if (path / obj).is_dir():
                        res[obj] = 'd'
                    else:
                        res[obj] = 'f'
                return res
            else:
                raise FileNotFoundError(f"错误：路径{user_path}不存在")
        raise PermissionError(f"错误：你只能查看基础目录中的内容")
    except Exception as e:
        raise Exception("服务器错误：", str(e))

@mcp.tool()
@logger
def search_file(pattern:str, user_path:str='./', types:str='f') -> dict[str, str]|str:
    """
    搜索文件或目录
    :param pattern: 正则表达式，用于匹配对象名称
    :param user_path: 从基础目录开始的路径，在指定的目录内搜素，默认为根路径
    :param types: 查找对象类型，f(文件), d(文件夹), a(文件+文件夹), 默认为f
    :return: {匹配到的对象的路径（从基础路径开始）: 对象类型(f是文件，d是文件夹)}
    """
    try:
        path = safe_path(user_path)
        try:
            regex = re.compile(pattern) # 编译正则表达式以加快匹配速度
        except re.error:
            raise ValueError("错误：无效的正则表达式")
        match_obj = {}  # 存放从基础目录开始的文件路径列表
        if path:
            # 使用os.walk()递归遍历目录树
            # root: 从path开始的完整路径（不包括文件名）
            # dirs: 当前目录中的所有文件夹
            # files: 当前目录中的所有文件
            for root, dirs, files in os.walk(str(path)):
                root = Path(root)
                if types == 'f':    # 类型为f：匹配文件
                    for filename in files:
                        if regex.search(filename):
                            match_obj[(str(Path.joinpath(root / filename)).split(str(BASE_PATH))[-1])] = 'f'
                elif types == 'd':  # 类型为d：匹配文件夹
                    for _dir in dirs:
                        if regex.search(_dir):
                            match_obj[(str(Path.joinpath(root, _dir)).split(str(BASE_PATH))[-1])] = 'd'
                else:   # 类型为a：匹配文件和文件夹
                    for filename in files:
                        if regex.search(filename):
                            match_obj[(str(Path.joinpath(root, filename)).split(str(BASE_PATH))[-1])] = 'f'
                    for _dir in dirs:
                        if regex.search(_dir):
                            match_obj[(str(Path.joinpath(root, _dir)).split(str(BASE_PATH))[-1])] = 'd'

            return match_obj
        else:
            raise PermissionError("错误：你只能查找基础目录中的内容")
    except Exception as e:
        raise Exception(f"服务器错误：{str(e)}")

@mcp.tool()
@logger
def clean_recovery(_id:str) -> str:
    """
    清空回收站或永久删除文件
    :param _id: 操作类型，支持三种模式：
                - 'ALL': 清空整个回收站（删除所有文件和数据库记录），慎用！
                - 'DATABASE': 清理数据库中的无效记录（文件已不存在但记录仍存在）
                - 具体ID: 永久删除指定 ID 的文件及其数据库记录
    :return: 操作结果消息
    """
    # 如果是ALL，清空回收站文件并清理数据库
    if _id == "ALL":
        # 清理磁盘文件
        if RECOVERY_PATH.exists():
            shutil.rmtree(RECOVERY_PATH)
        RECOVERY_PATH.mkdir(parents=True, exist_ok=True)
        # 清理数据库
        with sqlite3.connect("mcp.db") as conn:
            conn.cursor().execute("DELETE FROM recovery;")
            conn.commit()
        return "回收站已清空"

    elif _id == "DATABASE":
        # 清理数据库中无效的记录
        with sqlite3.connect("mcp.db") as conn:
            cursor = conn.cursor()
            rows = cursor.execute("SELECT id FROM recovery;").fetchall()
            # 使用生成器表达式解包为集合
            rows = {row[0] for row in rows}
            rec_dir = set(os.listdir(str(RECOVERY_PATH)))
            # 使用差集运算过滤数据库中有而实际回收站中没有的数据
            remnants = rows - rec_dir
            # 清除数据库中所有无效的数据
            for remnant in remnants:
                cursor.execute("DELETE FROM recovery WHERE id=?", (remnant,))
            conn.commit()
        return "数据库清理成功！"

    else:
        # 凭id删除回收站中对应文件
        with sqlite3.connect("mcp.db") as conn:
            cursor = conn.cursor()
            ori_path = cursor.execute("SELECT ori_path FROM recovery WHERE id=?", (_id,)).fetchall()[0][0]
            if os.path.exists(ori_path):
                os.remove(ori_path)
            cursor.execute("DELETE FROM recovery WHERE id=?", (_id,))
            conn.commit()
        return f"已永久删除文件{_id}"


if __name__ == "__main__":
    mcp.run()