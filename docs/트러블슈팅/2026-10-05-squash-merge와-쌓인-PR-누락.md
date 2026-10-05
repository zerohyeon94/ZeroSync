# 2026-10-05 — squash merge로 커밋 이력이 합쳐지고, 쌓인 PR이 develop에 들어가지 않음

> 상태: 해결 완료

---

## 증상

- PR #2(커밋 4개)를 develop에 merge했는데 develop 이력에는 커밋 1개(`f0bbdc8 ... (#2)`)만 보임
- PR #2 브랜치 위에 쌓은 PR #3(menubar/ 이동)을 merge했는데 develop에 menubar/ 이동이 반영되지 않음

```
재현 단계:
1. 저장소 설정이 "Squash merging만 허용, head 브랜치 자동 삭제 꺼짐"인 상태
2. PR A(대상 develop)와, PR A 브랜치를 대상으로 한 PR B를 만든다
3. PR A를 merge하고 곧바로 PR B를 merge한다
```

## 원인

- 저장소 설정에서 Squash merging만 허용되어 있었다. 운영 규약 4.6의 Merge commit 방식과 달랐다
- head 브랜치 자동 삭제가 꺼져 있어, PR A merge 후에도 PR A 브랜치가 남았다. GitHub는 대상 브랜치가 삭제될 때만 쌓인 PR의 대상을 develop으로 자동 변경하므로, PR B는 여전히 PR A 브랜치를 대상으로 merge되었다

## 해결

- 저장소 설정 변경: Merge commit만 허용(Squash·Rebase 끔), head 브랜치 자동 삭제 켬

```
gh api -X PATCH repos/zerohyeon94/ZeroSync \
  -F allow_merge_commit=true -F allow_squash_merge=false \
  -F allow_rebase_merge=false -F delete_branch_on_merge=true
```

- PR #3의 커밋 2개를 최신 develop 위에 cherry-pick해 PR #4로 다시 올리고 Merge commit으로 merge
- PR #2의 합쳐진 이력은 force push 금지 규칙에 따라 되돌리지 않음

## 재발 방지

- 새 저장소를 만들면 merge 정책(Merge commit만 허용, head 브랜치 자동 삭제)을 먼저 확인한다
- 쌓인 PR은 아래 PR이 merge되고 대상이 develop으로 바뀐 것을 확인한 뒤 merge한다

---

> 관련 PR: #2, #3, #4
> 관련 커밋: `f0bbdc8`, `81964ba`
