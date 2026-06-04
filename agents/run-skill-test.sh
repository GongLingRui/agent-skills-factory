#!/bin/bash
# Skill 隔离测试脚本 v3
# 核心改动：不用 --system-prompt（shell 参数有长度限制），改为全部内容通过 stdin 传入
set -e

SKILL_DIR="$1"
TEST_INPUT="$2"
OUTPUT_FILE="$3"
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_PATH="${BASE_DIR}/${SKILL_DIR}"

if [ -z "$SKILL_DIR" ] || [ -z "$TEST_INPUT" ] || [ -z "$OUTPUT_FILE" ]; then
    echo "用法: ./run-skill-test.sh <agent>/skill <test-input-file> <output-file>"
    echo "示例: ./run-skill-test.sh work-summary-agent/skill test/test-input-周报.md test/out.md"
    exit 1
fi

SKILL_MD="${SKILL_PATH}/SKILL.md"
INPUT_PATH="${SKILL_PATH}/${TEST_INPUT}"
OUTPUT_PATH="${SKILL_PATH}/${OUTPUT_FILE}"

if [ ! -f "$SKILL_MD" ]; then echo "错误: 找不到 ${SKILL_MD}"; exit 1; fi
if [ ! -f "$INPUT_PATH" ]; then echo "错误: 找不到 ${INPUT_PATH}"; exit 1; fi

echo "=== Skill 隔离测试 v3 ==="
echo "Skill: ${SKILL_DIR} | 输入: ${TEST_INPUT}"

# 组装完整消息到临时文件（SKILL 指令 + references + 测试输入）
COMBINED=$(mktemp /tmp/skill-test.XXXXXX.md)

cat >> "$COMBINED" << 'HEADER'
你是一个 AI Agent。以下是你必须严格遵循的 Skill 指令文档。请按照文档中的工作流，处理最下方的用户输入。

【测试模式】这是自动化测试。如果工作流中有用户确认步骤（检查点），请自动跳过，假设用户全部认可，直接输出最终交付物。不要输出中间确认环节。

===== SKILL 指令开始 =====
HEADER

cat "$SKILL_MD" >> "$COMBINED"

REF_DIR="${SKILL_PATH}/references"
if [ -d "$REF_DIR" ]; then
    for ref_file in "$REF_DIR"/*.md; do
        if [ -f "$ref_file" ]; then
            echo "" >> "$COMBINED"
            echo "--- Reference: $(basename "$ref_file") ---" >> "$COMBINED"
            cat "$ref_file" >> "$COMBINED"
        fi
    done
fi

cat >> "$COMBINED" << 'SEPARATOR'

===== SKILL 指令结束 =====

===== 用户输入开始 =====
SEPARATOR

cat "$INPUT_PATH" >> "$COMBINED"

echo "组装完成（$(wc -l < "$COMBINED") 行），发送中..."

# 通过 stdin 管道传入（无参数长度限制）
cat "$COMBINED" | claude --print --model sonnet --no-session-persistence > "$OUTPUT_PATH" 2>&1

rm -f "$COMBINED"
echo "=== 完成 → ${OUTPUT_FILE} ==="
