(globalThis.TURBOPACK || (globalThis.TURBOPACK = [])).push([typeof document === "object" ? document.currentScript : undefined,
"[project]/src/components/dot-reveal-grid.tsx [app-client] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "DotRevealGrid",
    ()=>DotRevealGrid
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/compiled/react/jsx-dev-runtime.js [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/compiled/react/index.js [app-client] (ecmascript)");
;
var _s = __turbopack_context__.k.signature();
"use client";
;
function DotRevealGrid() {
    _s();
    const [active, setActive] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])(false);
    const dots = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useMemo"])({
        "DotRevealGrid.useMemo[dots]": ()=>Array.from({
                length: 48
            }, {
                "DotRevealGrid.useMemo[dots]": (_, index)=>{
                    const col = index % 12;
                    const row = Math.floor(index / 12);
                    const x = col - 5.5;
                    const y = row - 1.5;
                    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        className: "landing-dot-matrix-dot",
                        style: {
                            ["--dot-x"]: x.toString(),
                            ["--dot-y"]: y.toString()
                        }
                    }, index, false, {
                        fileName: "[project]/src/components/dot-reveal-grid.tsx",
                        lineNumber: 17,
                        columnNumber: 11
                    }, this);
                }
            }["DotRevealGrid.useMemo[dots]"])
    }["DotRevealGrid.useMemo[dots]"], []);
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
        type: "button",
        className: "landing-dot-reveal-group absolute bottom-11 right-8 z-20 sm:bottom-14 sm:right-16",
        "aria-label": "Reveal self-healing software message",
        "data-active": active ? "true" : "false",
        onMouseEnter: ()=>setActive(true),
        onMouseLeave: ()=>setActive(false),
        onFocus: ()=>setActive(true),
        onBlur: ()=>setActive(false),
        onClick: ()=>setActive((current)=>!current),
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "landing-dot-reveal-content",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        className: "landing-dot-reveal-title",
                        children: "SELF-HEALING SOFTWARE"
                    }, void 0, false, {
                        fileName: "[project]/src/components/dot-reveal-grid.tsx",
                        lineNumber: 43,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        className: "landing-dot-reveal-pulse",
                        "aria-hidden": "true"
                    }, void 0, false, {
                        fileName: "[project]/src/components/dot-reveal-grid.tsx",
                        lineNumber: 44,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/src/components/dot-reveal-grid.tsx",
                lineNumber: 42,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "landing-dot-reveal-grid",
                "aria-hidden": "true",
                children: dots
            }, void 0, false, {
                fileName: "[project]/src/components/dot-reveal-grid.tsx",
                lineNumber: 46,
                columnNumber: 7
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/src/components/dot-reveal-grid.tsx",
        lineNumber: 31,
        columnNumber: 5
    }, this);
}
_s(DotRevealGrid, "VDVrM2gMUEJAMsq6xORqfhPTDwE=");
_c = DotRevealGrid;
var _c;
__turbopack_context__.k.register(_c, "DotRevealGrid");
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
]);

//# sourceMappingURL=src_components_dot-reveal-grid_tsx_9d63a467._.js.map