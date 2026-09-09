import { describe, expect, it } from "vitest"

import { ApiError, isApiError, normalizeError } from "@/lib/api/errors"

describe("normalizeError", () => {
  it("maps the backend envelope into an ApiError with field errors", () => {
    const err = normalizeError(
      { status: 422, statusText: "Unprocessable Entity" },
      {
        error: {
          code: "validation_error",
          message: "Some fields are invalid.",
          details: [
            { field: "email", message: "Invalid email" },
            { field: "password", message: "Too short" },
            { field: "email", message: "Duplicate should be ignored" },
          ],
        },
      }
    )

    expect(err).toBeInstanceOf(ApiError)
    expect(isApiError(err)).toBe(true)
    expect(err.status).toBe(422)
    expect(err.code).toBe("validation_error")
    expect(err.message).toBe("Some fields are invalid.")
    expect(err.fieldErrors).toEqual({
      email: "Invalid email",
      password: "Too short",
    })
  })

  it("falls back to a friendly message when the body is not an envelope", () => {
    const err = normalizeError(
      { status: 401, statusText: "Unauthorized" },
      null
    )
    expect(err.status).toBe(401)
    expect(err.code).toBe("unknown_error")
    expect(err.message).toBe("You need to sign in to continue.")
    expect(err.fieldErrors).toEqual({})
  })

  it("labels 5xx responses as server errors", () => {
    const err = normalizeError({ status: 503, statusText: "" }, "<html/>")
    expect(err.code).toBe("server_error")
    expect(err.message).toMatch(/try again/i)
  })
})
