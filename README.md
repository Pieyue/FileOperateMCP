# MCP 文件管理服务器

一个基于 FastMCP 构建的文件管理服务器，提供安全的文件读写、搜索、移动、复制、删除和恢复功能。

---

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置路径（可选）

编辑 `utils.py` 修改基础目录：

```python
BASE_PATH = Path(r'D:\LLM_Data\Data')      # 文件操作根目录
RECOVERY_PATH = Path(r"D:\LLM_Data\Recovery")  # 回收站目录
```
---

## 📂 项目结构

```
FileOperateMCP/
├── Data                 # LLM操作空间
├── Recovery             # 回收站
├── main.py              # 主程序，包含所有 Tool 实现
├── utils.py             # 工具函数（路径安全、ID生成、日志装饰器等）
├── mcp.db               # SQLite3 数据库（回收站元数据）
├── record.csv           # 操作日志文件
├── requirements.txt     # 依赖列表
└── README.md            # 项目文档
```

---

## 📋 项目简介

### 功能特性

- **安全的文件操作**：所有操作限制在沙箱目录内（`D:\LLM_Data\Data`），防止路径遍历攻击
- **灵活的文本读取**：支持按行号、范围、倒数等多种方式读取文本文件
- **二进制文件支持**：通过 Base64 编码安全传输二进制数据，支持前后字节读取
- **强大的文本搜索**：使用 Python 原生正则表达式引擎，跨平台兼容，防止命令注入
- **回收站机制**：删除的文件自动移动到回收站，可通过 ID 恢复
- **完整的日志记录**：所有操作自动记录到 CSV 日志文件，包含参数和结果
- **多编码支持**：自动检测和处理 UTF-8、GBK 等多种文件编码

### 技术实现

- **框架**：FastMCP (Model Context Protocol)
- **路径安全**：使用 `pathlib.Path.resolve()` 和 `relative_to()` 验证路径
- **ID 生成**：UUID4 前 20 位，几乎零碰撞概率
- **日志系统**：CSV 格式 + JSON 序列化参数，UTF-8-SIG 编码
- **数据库**：SQLite3 存储回收站元数据
- **错误处理**：统一的异常捕获和友好的错误消息

---

## 🛠️ Tools 列表

### 📑 目录

1. [read_file_content](#1-read_file_content) - 读取文件内容
2. [find_str](#2-find_str) - 文本搜索
3. [write_file_content](#3-write_file_content) - 写入文件内容
4. [move_file](#4-move_file) - 移动/重命名文件
5. [copy_file](#5-copy_file) - 复制文件
6. [delete_file](#6-delete_file) - 删除文件（回收站）
7. [recovery_file](#7-recovery_file) - 恢复文件
8. [clean_recovery](#8-clean_recovery) - 清空回收站/永久删除
9. [create_dir](#9-create_dir) - 创建目录
10. [list_dir](#10-list_dir) - 列出目录内容
11. [search_file](#11-search_file) - 搜索文件/目录

---

### 1. read_file_content

读取文件内容，支持文本和二进制模式。

**参数：**
- `user_path` (str): 相对于基础目录的文件路径
- `mode` (str, 默认='text'): 读取模式
  - `'text'`: 文本模式
  - `'binary'`: 二进制模式（返回 Base64 编码）
- `encoding` (str, 默认='utf-8'): 文本编码（仅 text 模式有效）
- `lines` (str, 默认=''): 行范围表达式（仅 text 模式有效）
  - `''`: 读取全部行（默认）
  - `'5'`: 第 5 行
  - `'-1'`: 倒数第 1 行
  - `'-5'`: 倒数 5 行
  - `'2-10'`: 第 2 到 10 行
  - `'2,6,4'`: 第 2、6、4 行
  - `'2-5 11,12'`: 第 2-5 行和第 11、12 行
- `bytes_count` (int|None, 默认=None): 字节数限制（仅 binary 模式有效）
  - `None`: 读取全部字节（默认）
  - 正整数: 读取前 N 个字节
  - 负整数: 读取倒数 N 个字节（-1 表示倒数 1 字节）

**返回：** 文件的文本内容或 Base64 编码的二进制数据

**示例：**
```python
# 读取全部文本
content = read_file_content('document.txt')

# 读取第 5 行
line5 = read_file_content('document.txt', lines='5')

# 读取最后 3 行
last3 = read_file_content('document.txt', lines='-3')

# 读取前 100 字节（二进制）
header = read_file_content('image.png', mode='binary', bytes_count=100)

# 读取最后 50 字节（二进制）
tail = read_file_content('data.bin', mode='binary', bytes_count=-50)
```

---

### 2. find_str

在文件中搜索匹配的文本（使用 Python 原生正则表达式，防止命令注入）。

**参数：**
- `user_path` (str): 从基础目录开始的路径（文件或目录）
- `regx` (str): 正则表达式字符串
- `ignore_ul` (bool, 默认=False): 是否忽略大小写
- `recursive` (bool, 默认=True): 是否递归搜索子目录

**返回：** 匹配结果字符串，格式为 `"文件路径:行号:匹配内容"`，每行一个匹配

**示例：**
```python
# 搜索包含 "error" 的行（区分大小写）
results = find_str('logs', 'error')

# 忽略大小写搜索
results = find_str('logs', 'ERROR', ignore_ul=True)

# 使用正则表达式搜索邮箱
results = find_str('contacts', r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

# 仅在当前目录搜索（不递归）
results = find_str('docs', 'TODO', recursive=False)
```

---

### 3. write_file_content

创建文件并向指定路径写入内容。

**参数：**
- `user_path` (str): 相对于基础目录的文件路径
- `content` (str, 默认=''): 要写入的内容
  - 文本模式：普通字符串
  - 二进制模式：Base64 编码的字符串
- `mode` (str, 默认='text'): 写入模式
  - `'text'`: 覆盖写入文本
  - `'append'`: 追加文本
  - `'binary'`: 覆盖写入二进制
  - `'append_binary'`: 追加二进制
- `encoding` (str, 默认='utf-8'): 编码方式（仅文本模式有效）

**返回：** 成功标志字符串（'文件创建成功' / '写入成功' / '追加成功' / '二进制写入成功' / '二进制追加成功'）

**示例：**
```python
# 写入文本文件
write_file_content('hello.txt', 'Hello World!')

# 追加文本
write_file_content('log.txt', 'New log entry\n', mode='append')

# 写入二进制文件（需要先 Base64 编码）
import base64
binary_data = b'\x89PNG\r\n\x1a\n'
base64_str = base64.b64encode(binary_data).decode('ascii')
write_file_content('image.png', base64_str, mode='binary')
```

---

### 4. move_file

移动文件或目录，如果在同一目录下则执行重命名。

**参数：**
- `src` (str): 源路径（从基础路径开始）
- `dst` (str): 目标路径（从基础路径开始）
- `override` (bool, 默认=False): 如果目标存在同名文件，是否覆盖

**返回：** '移动成功' 或 '重命名成功'

**示例：**
```python
# 移动文件到另一个目录
move_file('old_folder/file.txt', 'new_folder/file.txt')

# 重命名文件（同目录下移动）
move_file('document.txt', 'document_renamed.txt')

# 覆盖已存在的文件
move_file('file1.txt', 'file2.txt', override=True)
```

---

### 5. copy_file

复制文件或目录。

**参数：**
- `src` (str): 源路径（从基础路径开始）
- `dst` (str): 目标路径（从基础路径开始）
- `override` (bool, 默认=False): 如果目标存在同名文件，是否覆盖

**返回：** '成功'

**示例：**
```python
# 复制文件
copy_file('source.txt', 'backup/source_copy.txt')

# 复制目录
copy_file('folder', 'backup/folder_backup')

# 覆盖已存在的文件
copy_file('file1.txt', 'file2.txt', override=True)
```

---

### 6. delete_file

删除文件或目录（移动到回收站）。

**参数：**
- `user_path` (str): 从基础目录开始的待删除路径

**返回：** 包含恢复 ID 的成功消息

**示例：**
```python
# 删除文件
result = delete_file('unwanted.txt')
print(result)  # "成功！文件已删除，如果需要，你可以凭ID:abc123... 通过recovery_file恢复它们"

# 保存 ID 以备恢复
recovery_id = result.split('ID:')[1].split()[0]
```

---

### 7. recovery_file

通过删除时返回的 ID 恢复文件。

**参数：**
- `_id` (str): 删除文件时返回的 ID
- `override` (bool, 默认=False): 如果恢复时遇到重名文件，是否覆盖

**返回：** 成功恢复的消息

**示例：**
```python
# 恢复文件
result = recovery_file('abc123def456ghi789jk')
print(result)  # "成功恢复文件到\folder\file.txt"

# 覆盖已存在的文件
result = recovery_file('abc123def456ghi789jk', override=True)
```

---

### 8. clean_recovery

清空回收站或永久删除文件（不可恢复）。

**参数：**
- `_id` (str): 操作类型，支持三种模式：
  - `'ALL'`: 清空整个回收站（删除所有文件和数据库记录），慎用！
  - `'DATABASE'`: 清理数据库中的无效记录（文件已不存在但记录仍存在）
  - 具体ID: 永久删除指定 ID 的文件及其数据库记录

**返回：** 操作结果消息

**示例：**
```python
# 清空整个回收站（慎用！）
result = clean_recovery('ALL')
print(result)  # "回收站已完全清空"

# 清理数据库中的孤儿记录
result = clean_recovery('DATABASE')
print(result)  # "数据库清理成功！"

# 永久删除特定文件（不可恢复！）
result = clean_recovery('abc123def456ghi789jk')
print(result)  # "已永久删除文件 abc123def456ghi789jk"
```

**⚠️ 警告：**
- `clean_recovery('ALL')` 会**永久删除**回收站中的所有文件，无法恢复
- `clean_recovery('具体ID')` 会**永久删除**指定文件，无法恢复
- 建议先使用 `recovery_file()` 恢复需要的文件，再清空回收站

---

### 9. create_dir

创建文件夹（支持多级目录自动创建）。

**参数：**
- `user_path` (str): 从基础目录开始的路径

**返回：** '成功'

**示例：**
```python
# 创建单级目录
create_dir('new_folder')

# 创建多级目录
create_dir('parent/child/grandchild')
```

---

### 10. list_dir

列出目录中的所有对象。

**参数：**
- `user_path` (str, 默认='./'): 从基础目录开始的路径

**返回：** 字典 `{对象名: 类型}`，类型为 'f'（文件）或 'd'（文件夹）

**示例：**
```python
# 列出根目录
contents = list_dir()
# 返回: {'file1.txt': 'f', 'folder1': 'd', 'file2.py': 'f'}

# 列出指定目录
contents = list_dir('documents')
```

---

### 11. search_file

使用正则表达式搜索文件或目录名称。

**参数：**
- `pattern` (str): 正则表达式，用于匹配对象名称
- `user_path` (str, 默认='./'): 从基础目录开始的搜索路径
- `types` (str, 默认='f'): 查找对象类型
  - `'f'`: 仅文件
  - `'d'`: 仅文件夹
  - `'a'`: 文件 + 文件夹

**返回：** 字典 `{相对路径: 类型}`

**示例：**
```python
# 搜索所有 Python 文件
py_files = search_file(r'.*\.py$', types='f')
# 返回: {'src/main.py': 'f', 'utils/helper.py': 'f'}

# 搜索包含 "test" 的文件夹
test_dirs = search_file(r'test', types='d')

# 搜索所有对象
all_matches = search_file(r'readme', types='a')
```

---

## 🔒 安全特性

### 1. 路径沙箱
所有文件操作限制在 `BASE_PATH` (`D:\LLM_Data\Data`) 内，使用 `safe_path()` 函数验证：
```python
full_path = (BASE_PATH / path).resolve()
full_path.relative_to(BASE_PATH.resolve())  # 确保在沙箱内
```

### 2. 命令注入防护
`find_str` 使用 Python 原生 `re` 模块，不调用系统命令，完全防止命令注入攻击。

### 3. 正则表达式验证
所有接受正则表达式的函数都会先编译验证，捕获无效正则：
```python
try:
    pattern = re.compile(regx)
except re.error as e:
    raise ValueError(f"无效的正则表达式 - {str(e)}")
```

### 4. 唯一 ID 生成
使用 UUID4 前 20 位生成回收站 ID，碰撞概率极低（约 2^60 分之一）：
```python
_id = str(uuid.uuid4())[:20]
```

---

## 📝 日志系统

所有工具调用自动记录到 `record.csv` 文件：

**日志格式：**
```csv
func_name,args_str,kwargs_str,status,timestamp,error_msg
read_file_content,"[]","{""user_path"": ""test.txt"", ""lines"": ""5""}",Success,2024-01-01 12:00:00,
find_str,"[]","{""user_path"": ""logs"", ""regx"": ""error""}",Fail,2024-01-01 12:01:00,路径不存在
```

**特性：**
- CSV 格式，使用 `csv.writer` 保证格式正确
- JSON 序列化参数，避免特殊字符破坏格式
- UTF-8-SIG 编码，Excel 打开时中文正常显示
- 记录 args 和 kwargs，完整追踪调用信息

---

## 🗄️ 数据库结构

SQLite3 数据库 (`mcp.db`) 存储回收站元数据：

```sql
CREATE TABLE recovery (
    id       CHAR(20)      NOT NULL PRIMARY KEY UNIQUE,
    ori_path VARCHAR(1024) NOT NULL,
    datetime DATETIME
);
```

**字段说明：**
- `id`: 20 位唯一标识符（UUID4 前缀）
- `ori_path`: 原始文件路径（绝对路径）
- `datetime`: 删除时间

---

## ⚠️ 注意事项

1. **路径限制**：所有路径必须在 `BASE_PATH` 内，不允许使用 `..` 跳出
2. **编码问题**：文本文件默认使用 UTF-8，Windows 文件可能需要 GBK
3. **大文件处理**：读取大文件时使用 `lines` 或 `bytes_count` 限制范围
4. **回收站清理**：定期清理 `RECOVERY_PATH` 以释放磁盘空间
5. **日志轮转**：`record.csv` 会持续增长，建议定期归档

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

## 📄 许可证

MIT License

---

## 👨‍💻 作者

Pieyue
