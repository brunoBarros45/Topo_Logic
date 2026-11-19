import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium",
  {
    variants: {
      variant: {
        default:
          "border-[var(--border-subtle)] bg-[var(--bg-elevated)] text-[var(--text-primary)]",
        success: "border-emerald-500/40 bg-emerald-500/15 text-emerald-400",
        warning: "border-amber-500/40 bg-amber-500/15 text-amber-400",
        destructive: "border-red-500/40 bg-red-500/15 text-red-400",
        info: "border-sky-500/40 bg-sky-500/15 text-sky-400",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
