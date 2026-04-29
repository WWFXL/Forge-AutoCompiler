import { useMemo } from "react";

export function Footer() {
  const year = useMemo(() => new Date().getFullYear(), []);
  return (
    <footer className="container-md mx-auto mt-32 flex flex-col items-center justify-center border-t border-forge-border">
      <div className="text-gray-500 container flex h-20 flex-col items-center justify-center text-sm">
        <p className="text-center font-sans text-lg md:text-xl">
          &quot;Originated from Open Source, give back to Open Source.&quot;
        </p>
      </div>
      <div className="text-gray-500 container mb-8 flex flex-col items-center justify-center text-xs">
        <p>Licensed under MIT License</p>
        <p>&copy; {year} Forge</p>
      </div>
    </footer>
  );
}
