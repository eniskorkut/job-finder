import { cn } from "@/lib/cn";

export function Field({
  label,
  hint,
  error,
  htmlFor,
  children,
  className,
}: {
  label: string;
  hint?: string;
  error?: string | null;
  htmlFor?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <label
        htmlFor={htmlFor}
        className="text-[13px] leading-5 font-medium text-ink"
      >
        {label}
      </label>
      {children}
      {error ? (
        <p className="text-[12px] leading-4 text-danger">{error}</p>
      ) : hint ? (
        <p className="text-[12px] leading-4 text-ink-subtle">{hint}</p>
      ) : null}
    </div>
  );
}

const controlBase =
  "w-full rounded-[var(--radius-control)] bg-surface px-3 text-sm text-ink shadow-[var(--shadow-card)] outline-none transition-[box-shadow,background-color] duration-150 ease-out placeholder:text-ink-subtle focus-visible:shadow-[0_0_0_1px_var(--accent),0_0_0_4px_var(--accent-soft)] disabled:cursor-not-allowed disabled:opacity-60";

export function Input({
  className,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(controlBase, "h-9.5", className)} {...props} />;
}

export function Textarea({
  className,
  ...props
}: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(controlBase, "min-h-24 py-2 leading-6", className)}
      {...props}
    />
  );
}

export function Select({
  className,
  children,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        controlBase,
        "h-9.5 cursor-pointer appearance-none bg-[length:16px] bg-[right_0.6rem_center] bg-no-repeat pe-8",
        className,
      )}
      style={{
        backgroundImage:
          "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23888' stroke-width='1.5' stroke-linecap='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E\")",
      }}
      {...props}
    >
      {children}
    </select>
  );
}

export function Switch({
  checked,
  onCheckedChange,
  disabled,
  id,
  label,
}: {
  checked: boolean;
  onCheckedChange: (value: boolean) => void;
  disabled?: boolean;
  id?: string;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      id={id}
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        "relative inline-flex h-5.5 w-9.5 shrink-0 items-center rounded-full p-0.5",
        "transition-[background-color,box-shadow] duration-150 ease-out",
        "disabled:cursor-not-allowed disabled:opacity-50",
        checked
          ? "bg-accent"
          : "bg-surface-muted shadow-[var(--shadow-card)]",
      )}
    >
      <span
        aria-hidden
        className={cn(
          "size-4.5 rounded-full bg-white shadow-sm",
          "transition-[translate] duration-150 ease-out",
          checked ? "translate-x-4" : "translate-x-0",
        )}
        style={{ backgroundColor: checked ? "white" : "var(--ink-subtle)" }}
      />
    </button>
  );
}
