/// <reference types="vite/client" />

import type { Persona, Message } from '../../main/types'

interface ZABBridge {
  getApiKey: () => Promise<string>
  setApiKey: (key: string) => Promise<void>
  getHistory: (persona: Persona) => Promise<Message[]>
  clearHistory: (persona: Persona) => Promise<void>
  chat: (persona: Persona, message: string) => Promise<{ content?: string; error?: string }>
  sendNotification: (title: string, body: string) => Promise<void>
}

declare global {
  interface Window {
    zab: ZABBridge
    SpeechRecognition: typeof SpeechRecognition
    webkitSpeechRecognition: typeof SpeechRecognition
  }
}
