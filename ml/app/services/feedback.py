"""Общий фидбэк по попытке — один текст на всю попытку, а не на каждый вопрос.

Backend пишет его в student_attempts.overall_feedback, поэтому на выходе
обычный текст без JSON. LLM получает только промахи: хвалить за правильные
ответы незачем (студент и так видит score_pct), а пересказывать каждый вопрос
подряд незачем — ради этого фидбэк и один.

Если промахов нет, LLM не вызывается: сказать ему нечего, и он начнёт
выдумывать ошибки. Отдаём короткий текст-заглушку.
"""

from __future__ import annotations

from app.services.grader import Mistake
from app.services.llm import LLMClient

NO_MISTAKES_TEXT = (
    "Серьёзных ошибок нет — все ответы верные. "
    "Чтобы не терять форму, разберите на следующей неделе те вопросы, "
    "которые дались легче всего: так быстрее видеть свои слабые места, "
    "когда нагрузка растёт."
)

SYSTEM_PROMPT = (
    "Ты — преподаватель, который пишет разбор работы студенту.\n"
    "\n"
    "Правила:\n"
    "1. Ответ строго на русском языке, обращение на «ты».\n"
    "2. Объём — 3–5 предложений. Не список, а связный текст.\n"
    "3. Не хвали за правильные ответы и не перечисляй каждый вопрос подряд — "
    "студент и так видит свой балл.\n"
    "4. Говори о типовых ошибках и о том, что стоит повторить, опираясь "
    "только на материал блока <mistakes>...</mistakes>.\n"
    "5. Не выдумывай то, чего в блоке нет: тем, формул и тем, которых "
    "студент не путал.\n"
    "6. Без вступлений вроде «Вот ваш разбор» и без markdown-разметки — "
    "только сам текст фидбэка."
)

TASK_TEMPLATE = (
    "Студент прошёл тест и ошибся в {n} вопросах из {total}.\n"
    "Разбери его ошибки и напиши общий фидбэк.\n"
    "\n"
    "<mistakes>\n"
    "{block}\n"
    "</mistakes>\n"
)


def build_task(mistakes: list[Mistake], total_questions: int) -> str:
    lines: list[str] = []
    for i, m in enumerate(mistakes, start=1):
        lines.append(f"Вопрос {i}: {m.question}")
        lines.append(f"Ответ студента: {m.student_answer or 'нет ответа'}")
        lines.append(f"Правильный ответ: {m.correct_answer or 'не определён в тесте'}")
        if m.reason:
            lines.append(f"Примечание: {m.reason}")
        lines.append("")
    return TASK_TEMPLATE.format(
        n=len(mistakes), total=total_questions, block="\n".join(lines).strip()
    )


async def overall_feedback(llm: LLMClient, mistakes: list[Mistake], total_questions: int) -> str:
    if not mistakes:
        return NO_MISTAKES_TEXT
    answer = await llm.chat(SYSTEM_PROMPT, build_task(mistakes, total_questions))
    return answer.strip()