import { contextBridge, ipcRenderer } from 'electron'
import type { Persona, Message } from '../main/types'

contextBridge.exposeInMainWorld('zab', {
  getApiKey: (): Promise<string> => ipcRenderer.invoke('get-api-key'),
  setApiKey: (key: string): Promise<void> => ipcRenderer.invoke('set-api-key', key),
  getHistory: (persona: Persona): Promise<Message[]> => ipcRenderer.invoke('get-history', persona),
  clearHistory: (persona: Persona): Promise<void> => ipcRenderer.invoke('clear-history', persona),
  chat: (persona: Persona, message: string): Promise<{ content?: string; error?: string }> =>
    ipcRenderer.invoke('chat', persona, message),
  sendNotification: (title: string, body: string): Promise<void> =>
    ipcRenderer.invoke('send-notification', title, body),
})
