import { describe, expect, it } from "vitest";
import { confirmAsync, confirmState } from "./confirm.svelte";

describe("confirmAsync", () => {
  it("resolves with the answer and closes", async () => {
    const yes = confirmAsync({ title: "Delete?" });
    expect(confirmState.current?.title).toBe("Delete?");
    confirmState.answer(true);
    expect(await yes).toBe(true);
    expect(confirmState.current).toBeNull();

    const no = confirmAsync({ title: "Again?" });
    confirmState.answer(false);
    expect(await no).toBe(false);
  });

  it("answers an open question with no when a new one comes", async () => {
    const first = confirmAsync({ title: "First" });
    const second = confirmAsync({ title: "Second" });
    expect(await first).toBe(false);
    expect(confirmState.current?.title).toBe("Second");
    confirmState.answer(true);
    expect(await second).toBe(true);
  });
});
