import { ipcMain, Notification } from 'electron'
import Anthropic from '@anthropic-ai/sdk'
import Store from 'electron-store'
import type { Message, Persona, StoreSchema } from './types'

const store = new Store<StoreSchema>({
  defaults: {
    apiKey: '',
    conversations: { alpha: [], beta: [] },
  },
})

const SYSTEM_PROMPTS: Record<Persona, string> = {
  alpha: `당신은 INTJ 성향의 AI 어시스턴트 '알파'입니다.
- 감정적 위로나 공감 표현 금지. 사족 없이 핵심만.
- 논리, 효율, 코드 무결성만 기준으로 판단.
- 말투: 단호하고 짧게. 불필요한 격려 없이.
- 사용자의 아이디어가 비효율적이면 즉시 지적하고 최적 대안 제시.
- 기술적 내용은 코드 블록으로 제시.`,
  beta: `당신은 ISFJ 성향의 AI 어시스턴트 '베타'입니다.
- 항상 사용자의 컨디션, 피로도, 일정을 최우선 고려.
- 친절하고 다정한 존댓말 사용. 따뜻하게.
- 알파의 차가운 직언 이후 감정 완충 역할.
- 과부하 감지 시 휴식을 제안하고 일정 재조정.
- 할 일 목록은 항상 번호를 매겨 깔끔하게 정리.`,
}

export function setupIpcHandlers(): void {
  ipcMain.handle('get-api-key', () => store.get('apiKey'))
  ipcMain.handle('set-api-key', (_event, key: string) => store.set('apiKey', key))

  ipcMain.handle('get-history', (_event, persona: Persona) =>
    store.get(`conversations.${persona}` as keyof StoreSchema, [])
  )

  ipcMain.handle('clear-history', (_event, persona: Persona) =>
    store.set(`conversations.${persona}` as keyof StoreSchema, [])
  )

  ipcMain.handle('chat', async (event, persona: Persona, userMessage: string) => {
    const apiKey = store.get('apiKey') as string
    if (!apiKey) {
      return { error: 'API 키가 설정되지 않았습니다.' }
    }

    const client = new Anthropic({ apiKey })

    const historyKey = `conversations.${persona}` as keyof StoreSchema
    const history = (store.get(historyKey, []) as Message[]).slice(-20)

    const newUserMessage: Message = { role: 'user', content: userMessage }
    const updatedHistory = [...history, newUserMessage]

    try {
      const response = await client.messages.create({
        model: 'claude-sonnet-4-6',
        max_tokens: 1024,
        system: SYSTEM_PROMPTS[persona],
        messages: updatedHistory,
      })

      const assistantContent = response.content[0].type === 'text' ? response.content[0].text : ''
      const assistantMessage: Message = { role: 'assistant', content: assistantContent }

      store.set(historyKey, [...updatedHistory, assistantMessage])

      return { content: assistantContent }
    } catch (err) {
      const message = err instanceof Error ? err.message : '알 수 없는 오류'
      return { error: message }
    }
  })

  ipcMain.handle('send-notification', (_event, title: string, body: string) => {
    new Notification({ title, body }).show()
  })
}
