import { NextRequest } from "next/server";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";

export async function POST(
  request: NextRequest,
  { params }: { params: { journeyId: string } },
) {
  const body = await request.text();
  const upstream = await fetch(
    `${API_BASE_URL}/journeys/${params.journeyId}/listings/search`,
    {
      method: "POST",
      headers: {
        "content-type": "application/json",
        ...(request.headers.get("cookie")
          ? { cookie: request.headers.get("cookie") as string }
          : {}),
      },
      body,
      cache: "no-store",
    },
  );

  const responseText = await upstream.text();
  return new Response(responseText, {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "application/json",
    },
  });
}
