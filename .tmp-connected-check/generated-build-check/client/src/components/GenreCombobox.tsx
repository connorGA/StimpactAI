import { useState } from "react";
import { Check, ChevronsUpDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { GENRES, type GenreNode } from "@/lib/genres";

interface GenreComboboxProps {
  value: string;
  onValueChange: (value: string) => void;
  placeholder?: string;
  label?: string;
  id?: string;
  testId?: string;
}

export default function GenreCombobox({
  value,
  onValueChange,
  placeholder = "Search genres...",
  label,
  id,
  testId,
}: GenreComboboxProps) {
  const [open, setOpen] = useState(false);

  // Flatten all genres and sub-genres for searching
  const allGenres = GENRES.flatMap((genre) => [
    { label: genre.label, value: genre.value, isParent: true },
    ...(genre.children?.map((child) => ({
      label: `${genre.label} → ${child.label}`,
      value: child.value,
      isParent: false,
    })) || []),
  ]);

  const selectedGenre = allGenres.find((genre) => genre.value === value);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          id={id}
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="w-full justify-between"
          data-testid={testId}
        >
          {selectedGenre ? selectedGenre.label : placeholder}
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-full p-0" align="start">
        <Command>
          <CommandInput placeholder="Search genres..." />
          <CommandList>
            <CommandEmpty>No genre found.</CommandEmpty>
            {GENRES.map((genre) => (
              <CommandGroup key={genre.value} heading={genre.label}>
                <CommandItem
                  value={genre.value}
                  onSelect={() => {
                    onValueChange(genre.value);
                    setOpen(false);
                  }}
                  className="cursor-pointer"
                >
                  <Check
                    className={cn(
                      "mr-2 h-4 w-4",
                      value === genre.value ? "opacity-100" : "opacity-0"
                    )}
                  />
                  {genre.label}
                </CommandItem>
                {genre.children?.map((child) => (
                  <CommandItem
                    key={child.value}
                    value={`${genre.label} ${child.label} ${child.value}`}
                    onSelect={() => {
                      onValueChange(child.value);
                      setOpen(false);
                    }}
                    className="cursor-pointer pl-8"
                  >
                    <Check
                      className={cn(
                        "mr-2 h-4 w-4",
                        value === child.value ? "opacity-100" : "opacity-0"
                      )}
                    />
                    {child.label}
                  </CommandItem>
                ))}
              </CommandGroup>
            ))}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
