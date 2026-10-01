import { describe, expect, it } from "vitest";

import { resolveRedirect } from "@/proxy";

describe("proxy route gate", () => {
  it("sends anonymous visitors of app pages to the login screen", () => {
    expect(resolveRedirect({ pathname: "/jobs", hasSession: false })).toBe(
      "/login?next=%2Fjobs",
    );
    expect(
      resolveRedirect({ pathname: "/jobs", search: "?page=2", hasSession: false }),
    ).toBe("/login?next=%2Fjobs%3Fpage%3D2");
    expect(resolveRedirect({ pathname: "/preferences", hasSession: false })).toBe(
      "/login?next=%2Fpreferences",
    );
  });

  it("keeps the executive cockpit, login and invitation screens public", () => {
    expect(resolveRedirect({ pathname: "/", hasSession: false })).toBeNull();
    expect(resolveRedirect({ pathname: "/login", hasSession: false })).toBeNull();
    expect(
      resolveRedirect({ pathname: "/invite/token-abc", hasSession: false }),
    ).toBeNull();
  });

  it("does not bounce signed-in users out of the app", () => {
    expect(resolveRedirect({ pathname: "/", hasSession: true })).toBeNull();
    expect(resolveRedirect({ pathname: "/team", hasSession: true })).toBeNull();
  });

  it("skips the login screen when a session already exists", () => {
    expect(resolveRedirect({ pathname: "/login", hasSession: true })).toBe("/");
  });
});
