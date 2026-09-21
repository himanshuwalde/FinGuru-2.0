import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/supabase", () => ({
  supabase: {
    auth: {
      getSession: vi.fn(async () => ({
        data: { session: { access_token: "tok-123" } },
      })),
    },
  },
}));

import { apiFetch } from "@/lib/api";

describe("apiFetch", () => {
  it("attaches the bearer token from the Supabase session", async () => {
    const fetchMock = vi.fn(
      async () => new Response(JSON.stringify({ status: "ok" }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/health");

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toContain("/health");
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer tok-123");

    vi.unstubAllGlobals();
  });
});
