import express, { type Request, Response, NextFunction } from "express";
import { registerRoutes } from "./routes";
import { setupVite, serveStatic, log } from "./vite";

const app = express();

// Stripe webhook endpoint needs raw body for signature verification
// Apply JSON parsing conditionally - skip for webhook to preserve raw body
app.use((req, res, next) => {
  if (req.path === '/api/stripe-webhook') {
    // Use raw body parser for webhook
    express.raw({ type: 'application/json' })(req, res, next);
  } else {
    // Use JSON parser for all other routes
    next();
  }
});

// Apply JSON parsing for non-webhook routes
app.use((req, res, next) => {
  if (req.path === '/api/stripe-webhook') {
    next();
  } else {
    express.json()(req, res, next);
  }
});

app.use(express.urlencoded({ extended: false }));

// CSRF Protection Note:
// This application does not require traditional CSRF protection because:
// 1. Authentication uses JWT tokens in localStorage (not cookies)
// 2. All authenticated requests require explicit Authorization headers
// 3. Same-Origin Policy prevents cross-origin access to localStorage
// 4. Attackers cannot set custom Authorization headers from different origins
// Therefore, state-changing operations are already protected from CSRF attacks.

app.use((req, res, next) => {
  const start = Date.now();
  const path = req.path;

  res.on("finish", () => {
    const duration = Date.now() - start;
    if (path.startsWith("/api")) {
      // Log only method, path, status code, and duration (no response body to prevent PII exposure)
      const logLine = `${req.method} ${path} ${res.statusCode} in ${duration}ms`;
      log(logLine);
    }
  });

  next();
});

(async () => {
  try {
    console.log('🚀 Starting application initialization...');
    
    // Validate critical environment variables
    const requiredEnvVars = ['SESSION_SECRET', 'INTERNAL_WEBHOOK_SECRET', 'STRIPE_SECRET_KEY', 'STRIPE_WEBHOOK_SECRET'];
    const missingVars = requiredEnvVars.filter(varName => !process.env[varName]);
    
    if (missingVars.length > 0) {
      console.error('❌ Missing required environment variables:', missingVars.join(', '));
      console.error('💡 Please configure these in your Deployment settings');
    } else {
      console.log('✅ All required environment variables are set');
      console.log('🔐 Running in LIVE mode with Stripe production credentials');
    }

    // Register routes and initialize server
    console.log('📡 Registering API routes...');
    const server = await registerRoutes(app);
    console.log('✅ API routes registered successfully');

    // Error handling middleware
    app.use((err: any, _req: Request, res: Response, _next: NextFunction) => {
      const status = err.status || err.statusCode || 500;
      const message = err.message || "Internal Server Error";
      
      console.error('❌ Request error:', { status, message, stack: err.stack });
      res.status(status).json({ message });
    });

    // Setup Vite or static serving
    const env = app.get("env");
    console.log(`🌍 Environment: ${env}`);
    
    if (env === "development") {
      console.log('⚡ Setting up Vite development server...');
      await setupVite(app, server);
      console.log('✅ Vite development server ready');
    } else {
      console.log('📦 Serving static files for production...');
      serveStatic(app);
      console.log('✅ Static file serving configured');
    }

    // Start listening on port
    const port = parseInt(process.env.PORT || '5000', 10);
    console.log(`🔌 Attempting to bind to port ${port}...`);
    
    server.listen({
      port,
      host: "0.0.0.0",
      reusePort: true,
    }, () => {
      console.log(`✅ Server successfully started!`);
      log(`serving on port ${port}`);
    });

    // Handle server errors
    server.on('error', (error: any) => {
      console.error('❌ Server error:', error);
      if (error.code === 'EADDRINUSE') {
        console.error(`💡 Port ${port} is already in use. Please check if another process is running.`);
      }
    });

  } catch (error: any) {
    console.error('❌ Fatal error during application startup:', error);
    console.error('Stack trace:', error.stack);
    console.error('💡 The application failed to initialize. Please check the error above.');
    
    // Exit with error code in production to signal deployment failure
    if (process.env.NODE_ENV === 'production') {
      process.exit(1);
    }
  }
})();
