import type { SelectHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export function NativeSelect({
  className,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "h-8 w-full rounded-md border border-[var(--border-subtle)] bg-[var(--bg-app)] px-2 text-xs text-[var(--text-primary)] cursor-pointer disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}
