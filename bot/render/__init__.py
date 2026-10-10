"""스키마 객체를 사람이 읽는 텍스트로 바꾼다 (SPEC 6.1).

Discord에 의존하지 않는다. Discord 게시, Issue·PR 본문, 볼트 문서가 모두 이 계층을 쓴다.
"""

from bot.render.notice import render_notice
from bot.render.opinion import (
    MAX_POST_LENGTH,
    RenderedPost,
    render_format_error,
    render_opinion,
    render_opinion_post,
)

__all__ = [
    "MAX_POST_LENGTH",
    "RenderedPost",
    "render_format_error",
    "render_notice",
    "render_opinion",
    "render_opinion_post",
]
