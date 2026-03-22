import { NextRequest } from "next/server";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";

export async function GET(
  request: NextRequest,
  { params }: { params: { journeyId: string } },
) {
  const searchParams = request.nextUrl.searchParams.toString();
  const upstream = await fetch(
    `${API_BASE_URL}/journeys/${params.journeyId}/listings/address-suggest${searchParams ? `?${searchParams}` : ""}`,
    {
      method: "GET",
      headers: {
        ...(request.headers.get("cookie")
          ? { cookie: request.headers.get("cookie") as string }
          : {}),
      },
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
