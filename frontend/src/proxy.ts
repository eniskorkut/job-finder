import { NextResponse, type NextRequest } from "next/server";

export const SESSION_COOKIE = "jh_session";

const PUBLIC_PATHS = ["/", "/login", "/invite"];

/**
 * Pure decision helper so the routing rules are unit testable without a
 * running server. Returns the absolute path to redirect to, or null.
 */
export function resolveRedirect({
  pathname,
  search = "",
  hasSession,
}: {
  pathname: string;
  search?: string;
  hasSession: boolean;
}): string | null {
  const isPublic = PUBLIC_PATHS.some(
    (path) => pathname === path || pathname.startsWith(`${path}/`),
  );

  if (!hasSession && !isPublic) {
    const next = pathname === "/" ? "" : `?next=${encodeURIComponent(`${pathname}${search}`)}`;
    return `/login${next}`;
  }

  if (hasSession && pathname === "/login") {
    return "/";
  }

  return null;
}

/**
 * Cheap gate: a missing session cookie can never be authenticated, so the
 * redirect happens before any page renders. Real authorisation stays in the
 * API (the cookie value is only a hint here).
 */
export function proxy(request: NextRequest) {
  const target = resolveRedirect({
    pathname: request.nextUrl.pathname,
    search: request.nextUrl.search,
    hasSession: Boolean(request.cookies.get(SESSION_COOKIE)?.value),
  });

  if (target) {
    return NextResponse.redirect(new URL(target, request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!api|_next/static|_next/image|favicon.ico|icon.svg|robots.txt).*)",
  ],
};
