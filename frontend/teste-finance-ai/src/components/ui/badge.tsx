import { forwardRef, type HTMLAttributes } from "react";
import { cn } from "@/lib/cn";

type BadgeVariant = "default" | "secondary" | "outline" | "destructive";

export type BadgeProps = HTMLAttributes<HTMLSpanElement> & {
  variant?: BadgeVariant;
};

const variantClasses: Record<BadgeVariant, string> = {
  default: "bg-primary/15 text-primary border border-primary/25",
  secondary: "bg-muted text-foreground border border-border",
  outline: "bg-transparent text-foreground border border-border",
  destructive: "bg-destructive/15 text-destructive border border-destructive/25",
};

export const Badge = forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className, variant = "default", ...props }, ref) => {
    return (
      <span
        ref={ref}
        className={cn(
          "inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium leading-none",
          variantClasses[variant],
          className,
        )}
        {...props}
      />
    );
  },
);

Badge.displayName = "Badge";
