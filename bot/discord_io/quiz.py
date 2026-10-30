"""교육 주간 문제 버튼 (ADR-009).

버튼의 custom_id에 문제 번호와 고른 답을 담아 봇이 재시작해도 눌린다(DynamicItem).
누르면 클라이언트가 교육 데스크에 답을 넘기고, 결과와 해설은 누른 사람에게만 보인다.
"""

import re
from typing import Any

import discord

from bot.schemas import LETTERS

QUIZ_ID = re.compile(r"quiz:(?P<quiz>\d+):(?P<number>\d+):(?P<choice>[A-D])")


def quiz_custom_id(quiz_id: int, number: int, choice: str) -> str:
    return f"quiz:{quiz_id}:{number}:{choice}"


class QuizButton(discord.ui.DynamicItem[discord.ui.Button[Any]], template=QUIZ_ID.pattern):
    def __init__(self, quiz_id: int, number: int, choice: str):
        super().__init__(
            discord.ui.Button(
                label=choice,
                style=discord.ButtonStyle.secondary,
                custom_id=quiz_custom_id(quiz_id, number, choice),
            )
        )
        self.quiz_id = quiz_id
        self.number = number
        self.choice = choice

    @classmethod
    async def from_custom_id(
        cls, interaction: discord.Interaction, item: discord.ui.Item[Any], match: re.Match[str]
    ) -> "QuizButton":
        return cls(int(match["quiz"]), int(match["number"]), match["choice"])

    async def callback(self, interaction: discord.Interaction) -> None:
        client: Any = interaction.client
        await client.answer_quiz(interaction, self.quiz_id, self.number, self.choice)


def quiz_view(quiz_id: int, number: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    for letter in LETTERS:
        view.add_item(QuizButton(quiz_id, number, letter))
    return view
