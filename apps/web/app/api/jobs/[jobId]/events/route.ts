import { NextRequest } from "next/server";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";

export async function GET(
  request: NextRequest,
  { params }: { params: { jobId: string } },
) {
  const upstream = await fetch(`${API_BASE_URL}/jobs/${params.jobId}/events`, {
    method: "GET",
    headers: {
      ...(request.headers.get("cookie") ? { cookie: request.headers.get("cookie") as string } : {}),
      ...(request.headers.get("last-event-id")
        ? { "last-event-id": request.headers.get("last-event-id") as string }
        : {}),
    },
    cache: "no-store",
  });

  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "content-type": "text/event-stream",
      "cache-control": "no-cache",
      connection: "keep-alive",
    },
  });
}
