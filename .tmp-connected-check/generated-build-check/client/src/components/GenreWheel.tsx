import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { GENRES, GenreNode } from "@/lib/genres";
import { Music, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

interface GenreWheelProps {
  value: string;
  onValueChange: (value: string) => void;
}

export default function GenreWheel({ value, onValueChange }: GenreWheelProps) {
  const [expandedGenre, setExpandedGenre] = useState<string | null>(null);

  const mainGenres = GENRES;

  const handleGenreClick = (genre: GenreNode) => {
    if (expandedGenre === genre.value) {
      // Collapse if already expanded
      setExpandedGenre(null);
    } else {
      // Expand to show sub-genres
      setExpandedGenre(genre.value);
    }
  };

  const handleSubGenreClick = (parentValue: string, childValue: string) => {
    onValueChange(`${parentValue}:${childValue}`);
  };

  const isSelected = (genreValue: string, subGenreValue?: string) => {
    if (subGenreValue) {
      return value === `${genreValue}:${subGenreValue}`;
    }
    return value.startsWith(genreValue);
  };

  const getSelectedLabel = () => {
    if (!value) return "Select a genre";
    
    const [parentValue, childValue] = value.split(":");
    const parent = mainGenres.find(g => g.value === parentValue);
    if (!parent) return "Select a genre";
    
    if (childValue && parent.children) {
      const child = parent.children.find(c => c.value === childValue);
      if (child) return `${parent.label} → ${child.label}`;
    }
    
    return parent.label;
  };

  // Colors for different genres (cycling through a palette)
  const genreColors = [
    "bg-primary",
    "bg-orange-500",
    "bg-purple-500",
    "bg-teal-500",
    "bg-red-500",
    "bg-blue-500",
    "bg-yellow-500",
    "bg-pink-500",
  ];

  const expandedGenreData = expandedGenre ? mainGenres.find(g => g.value === expandedGenre) : null;

  return (
    <div className="flex flex-col items-center gap-3 sm:gap-4">
      {/* Selected genre display */}
      <div className="text-center w-full max-w-md">
        <div className="text-xs sm:text-sm text-muted-foreground mb-1">Selected Genre:</div>
        <div className="text-sm sm:text-lg font-semibold text-foreground flex items-center justify-center gap-2 min-w-0">
          <Music className="h-4 w-4 sm:h-5 sm:w-5 text-primary shrink-0" />
          <span className="truncate min-w-0">{getSelectedLabel()}</span>
        </div>
      </div>

      {/* Genre wheel - List-based approach with visual wheel styling */}
      <div className="w-full max-w-md space-y-2 sm:space-y-3">
        {/* Main genres */}
        <div className="grid grid-cols-2 gap-1.5 sm:gap-2">
          {mainGenres.map((genre, index) => {
            const isExpanded = expandedGenre === genre.value;
            const selected = isSelected(genre.value);
            const colorClass = genreColors[index % genreColors.length];
            
            return (
              <div key={genre.value} className="space-y-1.5 sm:space-y-2">
                <Button
                  type="button"
                  variant={selected ? "default" : "outline"}
                  className={`w-full justify-between text-xs sm:text-sm ${!selected ? colorClass + ' text-white hover:opacity-90' : ''}`}
                  onClick={() => handleGenreClick(genre)}
                  data-testid={`genre-button-${genre.value}`}
                >
                  <span className="font-semibold truncate min-w-0">{genre.label}</span>
                  <ChevronRight className={`h-3 w-3 sm:h-4 sm:w-4 shrink-0 transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
                </Button>

                {/* Sub-genres (expanded) */}
                <AnimatePresence>
                  {isExpanded && genre.children && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2 }}
                      className="overflow-hidden space-y-0.5 sm:space-y-1 pl-2 sm:pl-4"
                    >
                      {genre.children.map((child) => {
                        const childSelected = isSelected(genre.value, child.value);
                        
                        return (
                          <Button
                            key={child.value}
                            type="button"
                            variant={childSelected ? "default" : "ghost"}
                            size="sm"
                            className="w-full justify-start text-xs sm:text-sm"
                            onClick={() => handleSubGenreClick(genre.value, child.value)}
                            data-testid={`subgenre-button-${child.value}`}
                          >
                            <span className="truncate min-w-0">{child.label}</span>
                          </Button>
                        );
                      })}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            );
          })}
        </div>
      </div>

      {/* Instructions */}
      <p className="text-[11px] sm:text-xs text-muted-foreground text-center max-w-sm px-2">
        Click a genre to expand and see sub-genres. Click a sub-genre to select it.
      </p>

      {/* Popular sub-genres quick access (if no genre expanded) */}
      {!expandedGenre && (
        <div className="w-full max-w-md">
          <p className="text-xs sm:text-sm font-medium mb-1.5 sm:mb-2">Popular Styles:</p>
          <div className="flex flex-wrap gap-1.5 sm:gap-2">
            {[
              { parent: "electronic", child: "synthwave", label: "Synthwave" },
              { parent: "hip-hop", child: "trap", label: "Trap" },
              { parent: "rock", child: "indie-rock", label: "Indie Rock" },
              { parent: "pop", child: "hyperpop", label: "Hyperpop" },
              { parent: "rnb-soul", child: "neo-soul", label: "Neo-Soul" },
              { parent: "electronic", child: "vaporwave", label: "Vaporwave" },
            ].map((quick) => (
              <Badge
                key={`${quick.parent}:${quick.child}`}
                variant={value === `${quick.parent}:${quick.child}` ? "default" : "outline"}
                className="cursor-pointer hover-elevate max-w-full min-w-0 text-xs sm:text-sm"
                onClick={() => onValueChange(`${quick.parent}:${quick.child}`)}
                data-testid={`quick-genre-${quick.child}`}
              >
                <span className="truncate min-w-0">{quick.label}</span>
              </Badge>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
