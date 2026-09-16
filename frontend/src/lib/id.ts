/** Sinh id ngẫu nhiên, có fallback cho trình duyệt không hỗ trợ crypto.randomUUID. */
export function createId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}
