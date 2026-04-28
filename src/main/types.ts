export type Persona = 'alpha' | 'beta'

export interface Message {
  role: 'user' | 'assistant'
  content: string
}

export interface StoreSchema {
  apiKey: string
  conversations: {
    alpha: Message[]
    beta: Message[]
  }
}
