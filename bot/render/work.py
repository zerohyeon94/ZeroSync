"""Phase 2 렌더링: Issue, 설계, 테스트, 리뷰, PR 본문 (운영 규약 1.8, 1.9, 2.3).

Discord·GitHub 모두 마크다운을 쓰므로 같은 함수를 쓴다. Discord에 의존하지 않는다.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from bot.schemas import DesignSummary, Finding, ImplementationReport, Opinion, Review
from bot.testrun import TestReport


@dataclass(frozen=True)
class ReviewRound:
    round: int
    review: Review


def _bullets(items: Sequence[str]) -> list[str]:
    return [f"- {item}" for item in items]


def render_issue_body(
    *,
    decision: str,
    post: str,
    opinions: Sequence[tuple[str, Opinion]],
    discord_url: str | None,
) -> str:
    """Issue 본문은 봇이 기존 텍스트로 조립한다 (운영 규약 1.8)."""
    lines = ["## 결정", "", decision.strip(), "", "## 배경", "", post.strip(), ""]
    if opinions:
        lines += ["## 의견 요약", ""]
        for name, opinion in opinions:
            lines.append(f"**{name}** — {opinion.stance.label}: {opinion.conclusion}")
            lines += [f"- 위험: {risk}" for risk in opinion.risks]
            lines.append("")
    lines += ["## 링크", "", f"- Discord 게시글: {discord_url or '-'}", ""]
    lines.append("_ZeroSync 봇이 만든 Issue_")
    return "\n".join(lines)


def render_design(summary: DesignSummary, *, doc_url: str | None = None) -> str:
    lines = [
        f"**설계** — {summary.conventional_title}",
        "",
        f"변경 유형: {summary.change_type.label} · 대상 기능: {summary.target_feature}",
        "",
        summary.summary,
        "",
        "바꿀 것",
        *_bullets(summary.changes),
        "",
        "테스트 계획",
        *_bullets(summary.test_plan),
    ]
    if summary.risks:
        lines += ["", "위험", *_bullets(summary.risks)]
    lines += ["", f"설계 전문: {doc_url or summary.design_doc}"]
    return "\n".join(lines)


def render_implementation(report: ImplementationReport, *, heading: str = "구현") -> str:
    lines = [f"**{heading}** — {report.changes_summary}", "", f"설계 의도: {report.design_intent}"]
    if report.check_points:
        lines += ["", "확인할 점", *_bullets(report.check_points)]
    if report.responses:
        lines += ["", "지적별 대응"]
        lines += [f"- {r.index}. {r.action.label}: {r.note}" for r in report.responses]
    return "\n".join(lines)


def render_test_report(report: TestReport) -> str:
    if report.passed:
        head = f"**테스트 통과** — {report.total if report.total is not None else '?'}개"
    else:
        head = "**테스트 실패**"
        if report.failures:
            head += f" — 실패 {report.failures}개 / 전체 {report.total}개"
    lines = [f"{head} ({report.duration_sec}초)"]
    if report.failed_tests:
        lines += ["", "실패한 테스트", *_bullets(report.failed_tests)]
    if report.errors:
        lines += ["", "오류", *(f"- `{error}`" for error in report.errors)]
    return "\n".join(lines)


def render_findings(findings: Sequence[Finding]) -> str:
    """번호를 붙인 지적 목록. FIX 단계의 responses.index가 이 번호를 가리킨다."""
    lines = []
    for index, finding in enumerate(findings, start=1):
        where = ""
        if finding.file:
            where = f" `{finding.file}{f':{finding.line}' if finding.line else ''}`"
        lines.append(f"{index}. {finding.severity.label}{where} {finding.problem}")
        lines.append(f"   - 이유: {finding.reason}")
        lines.append(f"   - 제안: {finding.suggestion}")
    return "\n".join(lines)


def render_review(review: Review, *, round_: int) -> str:
    required = len(review.required_findings)
    recommended = len(review.recommended_findings)
    lines = [
        f"**리뷰 {round_}라운드: {review.verdict.value}** — {review.summary}",
        f"[필수] {required}개 · [권장] {recommended}개",
    ]
    if review.findings:
        lines += ["", render_findings(review.findings)]
    return "\n".join(lines)


def render_pr_body(
    *,
    decision: str,
    summary: DesignSummary,
    report: ImplementationReport | None,
    tests: TestReport | None,
    reviews: Sequence[ReviewRound],
    discord_url: str | None,
    branch: str,
    issue: int,
) -> str:
    """PR 본문 (운영 규약 1.9). 변경 요약·설계 의도·확인할 점은 Beta의 구현 보고에서 온다."""
    lines = ["## 결정", "", decision.strip(), ""]
    if report is not None:
        lines += ["## 변경 요약", "", report.changes_summary, ""]
        lines += ["## 설계 의도", "", report.design_intent, ""]
        if report.check_points:
            lines += ["## 확인할 점", "", *_bullets(report.check_points), ""]
    lines += ["## 설계", "", f"`{summary.design_doc}` — {summary.summary}", ""]
    lines += ["## 테스트", "", render_test_report(tests) if tests else "아직 실행 전", ""]
    lines += ["## 리뷰 이력", ""]
    if reviews:
        lines += [
            f"- {r.round}라운드: {r.review.verdict.value} — {r.review.summary}" for r in reviews
        ]
    else:
        lines.append("- 아직 없음")
    lines += [
        "",
        "## 링크",
        "",
        f"- Discord 게시글: {discord_url or '-'}",
        f"- 브랜치: `{branch}`",
        "",
        f"Refs #{issue}",
    ]
    return "\n".join(lines)
