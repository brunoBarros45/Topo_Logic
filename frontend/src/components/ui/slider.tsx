import * as SliderPrimitive from "@radix-ui/react-slider";
import type { ComponentPropsWithoutRef } from "react";

import { cn } from "@/lib/utils";

export function Slider({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof SliderPrimitive.Root>) {
  return (
    <SliderPrimitive.Root
      className={cn(
        "relative flex w-full touch-none select-none items-center py-1.5",
        className,
      )}
      {...props}
    >
      <SliderPrimitive.Track className="relative h-1.5 w-full grow overflow-hidden rounded-full bg-[var(--bg-elevated)] border border-[var(--border-subtle)]">
        <SliderPrimitive.Range className="absolute h-full bg-[var(--accent-primary)]" />
      </SliderPrimitive.Track>
      <SliderPrimitive.Thumb className="block h-3.5 w-3.5 rounded-full border-2 border-[var(--accent-primary)] bg-[var(--bg-panel)] shadow transition-transform hover:scale-110 cursor-pointer" />
    </SliderPrimitive.Root>
  );
}
