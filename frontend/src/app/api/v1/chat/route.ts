import { NextRequest, NextResponse } from "next/server";

// Allow up to 5 minutes for slow LLM agent responses (Vercel / production)
export const maxDuration = 300;

export async function POST(request: NextRequest): Promise<NextResponse> {
  const body = await request.text();

  const forwardHeaders: HeadersInit = { "Content-Type": "application/json" };
  const apiKey = request.headers.get("X-API-Key");
  if (apiKey) forwardHeaders["X-API-Key"] = apiKey;

  const backendUrl =
    process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  try {
    // Node.js fetch has no default timeout — waits as long as needed
    const upstream = await fetch(`${backendUrl}/api/v1/chat`, {
      method: "POST",
      headers: forwardHeaders,
      body,
    });

    const data = await upstream.text();
    return new NextResponse(data, {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch (err) {
    console.error("[chat proxy] upstream error:", err);
    return NextResponse.json(
      { detail: "Failed to reach backend." },
      { status: 502 }
    );
  }
}
