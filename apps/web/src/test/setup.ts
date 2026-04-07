import "@testing-library/jest-dom/vitest";
import { createElement } from "react";
import { cleanup, act } from "@testing-library/react";
import { notifyManager } from "@tanstack/react-query";
import { afterEach, vi } from "vitest";

notifyManager.setNotifyFunction((callback) => {
  act(() => {
    callback();
  });
});

vi.mock("recharts", async () => {
  const actual = await vi.importActual<typeof import("recharts")>("recharts");

  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children?: React.ReactNode }) =>
      createElement(
        "div",
        {
          "data-testid": "recharts-responsive-container",
          style: { width: "100%", height: "100%", minWidth: "1px", minHeight: "1px" },
        },
        children,
      ),
  };
});

afterEach(() => {
  cleanup();
});
