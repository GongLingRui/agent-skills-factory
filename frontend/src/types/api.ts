export interface ApiError {
  error: {
    code: string
    message: string
    request_id?: string
  }
}
