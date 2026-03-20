import { NextRequest } from "next/server";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";

export async function POST(request: NextRequest) {
  const body = await request.text();
  const upstream = await fetch(`${API_BASE_URL}/journeys`, {
    method: "POST",
    headers: {
      "content-type": request.headers.get("content-type") ?? "application/json",
      ...(request.headers.get("cookie") ? { cookie: request.headers.get("cookie") as string } : {}),
    },
    body,
    cache: "no-store",
  });

  const responseText = await upstream.text();
  const headers = new Headers();
  const contentType = upstream.headers.get("content-type");
  const setCookie = upstream.headers.get("set-cookie");

  if (contentType) {
    headers.set("content-type", contentType);
  }
  if (setCookie) {
    headers.set("set-cookie", setCookie);
  }

  return new Response(responseText, {
    status: upstream.status,
    headers,
  });
}