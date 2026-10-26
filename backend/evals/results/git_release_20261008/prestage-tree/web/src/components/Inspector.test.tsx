import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { demoDays } from "../data/demoData";
import { Inspector } from "./Inspector";


describe("Inspector activity importance", () => {
  it("edits importance with product language and saves the repository payload", async () => {
    const user = userEvent.setup();
    const activity = { ...demoDays[0].activities[0], importance: "normal" as const };
    const onSave = vi.fn().mockResolvedValue(undefined);

    render(
      <Inspector
        activity={activity}
        days={demoDays}
        currentDayId={demoDays[0].id}
        busy={false}
        onClose={vi.fn()}
        onRemove={vi.fn()}
        onSave={onSave}
        onMove={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    await user.click(screen.getByRole("button", { name: "编辑活动" }));
    await user.selectOptions(screen.getByLabelText("重要程度"), "must_do");
    expect(screen.getByLabelText("时间紧张时可以跳过")).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "保存修改" }));

    expect(onSave).toHaveBeenCalledWith(
      activity.id,
      expect.objectContaining({ version: activity.version, importance: "must_do", canSkip: false }),
    );
  });

  it("shows a lightweight must-do tag on the activity detail", () => {
    render(
      <Inspector
        activity={{ ...demoDays[0].activities[0], importance: "must_do" }}
        days={demoDays}
        currentDayId={demoDays[0].id}
        busy={false}
        onClose={vi.fn()}
        onRemove={vi.fn()}
        onSave={vi.fn()}
        onMove={vi.fn()}
      />,
    );

    expect(screen.getByText("必去")).toBeInTheDocument();
  });

  it("edits non-skippable and minimum-stay semantics and shows them after reload", async () => {
    const user = userEvent.setup();
    const activity = { ...demoDays[0].activities[0], canSkip: true, minimumDurationMinutes: null };
    const onSave = vi.fn().mockResolvedValue(undefined);
    const props = {
      activity, days: demoDays, currentDayId: demoDays[0].id, busy: false,
      onClose: vi.fn(), onRemove: vi.fn(), onSave, onMove: vi.fn().mockResolvedValue(undefined),
    };
    const view = render(<Inspector {...props} />);
    await user.click(screen.getByRole("button", { name: "编辑活动" }));
    await user.click(screen.getByLabelText("时间紧张时可以跳过"));
    await user.type(screen.getByLabelText("最少停留（分钟）"), "60");
    await user.click(screen.getByRole("button", { name: "保存修改" }));
    expect(onSave).toHaveBeenCalledWith(activity.id, expect.objectContaining({ canSkip: false, minimumDurationMinutes: 60 }));

    view.rerender(<Inspector {...props} activity={{ ...activity, canSkip: false, minimumDurationMinutes: 60, version: activity.version + 1 }} />);
    expect(screen.getByText("时间不够也要保留")).toBeInTheDocument();
    expect(screen.getByText("至少游览 60 分钟")).toBeInTheDocument();
  });
});
