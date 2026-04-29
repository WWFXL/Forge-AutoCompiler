import { cn } from "@/lib/utils";

export function Section({
  className,
  title,
  subtitle,
  children,
}: {
  className?: string;
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className={cn("mx-auto flex flex-col py-16", className)}>
      <header className="flex flex-col items-center justify-between">
        <div className="mb-4 text-center text-5xl font-bold font-display text-white">
          {title}
        </div>
        {subtitle && (
          <div className="text-gray-400 text-center text-xl">
            {subtitle}
          </div>
        )}
      </header>
      <main className="mt-4">{children}</main>
    </section>
  );
}
