import { useEffect, useId, useRef, type ReactNode } from "react";
import { X } from "lucide-react";

import { Button } from "@/components/ui/button";

export interface NativeDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  children: ReactNode;
}

/**
 * Accessible modal dialog backed natively by HTML `<dialog>` + `.showModal()`.
 * Relies on browser top-layer promotion, Esc handling, and outside pointer bounds light-dismiss.
 */
export function NativeDialog({
  open,
  onOpenChange,
  title,
  children,
}: NativeDialogProps) {
  const ref = useRef<HTMLDialogElement | null>(null);
  const pressedOutsideRef = useRef(false);
  const titleId = useId();

  useEffect(() => {
    const dlg = ref.current;
    if (!dlg) return;
    if (open && !dlg.open) {
      dlg.showModal();
    } else if (!open && dlg.open) {
      dlg.close();
    }
  }, [open]);

  const isOutside = (e: React.PointerEvent<HTMLDialogElement>, dlg: HTMLDialogElement) => {
    const r = dlg.getBoundingClientRect();
    return (
      e.clientX < r.left ||
      e.clientX > r.right ||
      e.clientY < r.top ||
      e.clientY > r.bottom
    );
  };

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClose={() => {
        if (ref.current) {
          ref.current.returnValue = "";
        }
        onOpenChange(false);
      }}
      onPointerDown={(e) => {
        const dlg = ref.current;
        pressedOutsideRef.current = dlg ? isOutside(e, dlg) : false;
      }}
      onPointerUp={(e) => {
        const dlg = ref.current;
        if (dlg && pressedOutsideRef.current && isOutside(e, dlg)) {
          dlg.close();
        }
        pressedOutsideRef.current = false;
      }}
      className="m-auto w-full max-w-md rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-panel)] p-4 text-[var(--text-primary)] shadow-2xl"
    >
      <div className="flex items-center justify-between border-b border-[var(--border-subtle)] pb-2.5 mb-3">
        <h2 id={titleId} className="text-sm font-semibold">
          {title}
        </h2>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Close"
          onClick={() => ref.current?.close()}
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
      {children}
    </dialog>
  );
}
