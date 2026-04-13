import type { Express } from "express";
import { createServer, type Server } from "http";
import { storage } from "./storage";
import multer from "multer";
import { requireAuth, requireAdmin } from "./authMiddleware";
import Stripe from "stripe";
import { CREDIT_PACKAGES, PLAN_LIMITS, type PlanTier } from "../shared/schema.js";
import { uploadAudioToS3, uploadCoverToS3, uploadPlaylistCoverToS3, generateSignedUrl } from "./s3Upload";
import express from "express";
import rateLimit from "express-rate-limit";

// Xano API Configuration - matches client configuration
const XANO_AUTH_BASE_URL = 'https://xvaz-5ufg-teim.n7e.xano.io/api:rVbvzJH3';
const XANO_DATA_BASE_URL = 'https://xvaz-5ufg-teim.n7e.xano.io/api:SuvYKY7H';

// Internal webhook secret for server-to-server authentication
// This secret is used to secure internal endpoints that handle webhook operations
if (!process.env.INTERNAL_WEBHOOK_SECRET) {
  throw new Error('Missing required secret: INTERNAL_WEBHOOK_SECRET. Please set this environment variable.');
}
const INTERNAL_WEBHOOK_SECRET = process.env.INTERNAL_WEBHOOK_SECRET;

// In-memory lock for atomic credit operations to prevent race conditions
const creditLocks = new Map<string, Promise<void>>();

// In-memory set to track processed Stripe checkout sessions for idempotency
// NOTE: This is stored in-memory and will not persist across server restarts or
// multiple instances. For production deployments with multiple instances or high
// availability requirements, replace this with a persistent store (Redis/Database)
// to prevent duplicate credit grants on webhook retries after restarts.
const processedCheckoutSessions = new Set<string>();

// Rate limiting for webhook endpoints to prevent abuse
const webhookRateLimiter = rateLimit({
  windowMs: 1 * 60 * 1000, // 1 minute window
  max: 100, // Limit each IP to 100 requests per windowMs
  message: 'Too many webhook requests from this IP, please try again later.',
  standardHeaders: true, // Return rate limit info in the `RateLimit-*` headers
  legacyHeaders: false, // Disable the `X-RateLimit-*` headers
});

// Middleware to verify internal webhook requests
function verifyInternalWebhookSecret(req: any, res: any, next: any) {
  const secret = req.headers['x-webhook-secret'];

  if (!secret || secret !== INTERNAL_WEBHOOK_SECRET) {
    console.error('Unauthorized internal webhook request');
    return res.status(403).json({ error: 'Forbidden' });
  }

  next();
}

// Initialize Stripe with live credentials
const stripeSecretKey = process.env.STRIPE_SECRET_KEY;
if (!stripeSecretKey) {
  throw new Error('Missing required Stripe secret: STRIPE_SECRET_KEY');
}
const stripe = new Stripe(stripeSecretKey, {
  apiVersion: "2025-09-30.clover",
});

// Log which Stripe mode we're using
console.log(`🔐 Stripe initialized in LIVE mode`);

// Configure multer for file uploads using memory storage (for S3 upload)
const upload = multer({
  storage: multer.memoryStorage(),
  limits: {
    fileSize: 50 * 1024 * 1024, // 50MB limit
  },
});

// Helper: Get user by Stripe customer ID using filtered query
async function getUserByStripeCustomerId(customerId: string): Promise<any | null> {
  try {
    // Query account_status with filter
    const accountStatusUrl = `${XANO_DATA_BASE_URL}/account_status?stripe_customer_id=${encodeURIComponent(customerId)}`;
    const accountStatusResponse = await fetch(accountStatusUrl);

    if (!accountStatusResponse.ok) {
      console.error('Failed to fetch account status by customer ID');
      return null;
    }

    const accountStatuses = await accountStatusResponse.json();
    const accountStatus = Array.isArray(accountStatuses) && accountStatuses.length > 0
      ? accountStatuses[0]
      : null;

    if (!accountStatus) {
      return null;
    }

    // Get the user by user_id with filter
    const userUrl = `${XANO_AUTH_BASE_URL}/user?id=${encodeURIComponent(accountStatus.user_id)}`;
    const userResponse = await fetch(userUrl);

    if (!userResponse.ok) {
      console.error('Failed to fetch user by ID');
      return null;
    }

    const users = await userResponse.json();
    return Array.isArray(users) && users.length > 0 ? users[0] : null;
  } catch (error) {
    console.error('Error in getUserByStripeCustomerId:', error);
    return null;
  }
}

// Helper: Get user by ID using filtered query
async function getUserById(userId: string): Promise<any | null> {
  try {
    const userUrl = `${XANO_AUTH_BASE_URL}/user?id=${encodeURIComponent(userId)}`;
    const userResponse = await fetch(userUrl);

    if (!userResponse.ok) {
      console.error(`Failed to fetch user by ID. Status: ${userResponse.status}`);
      return null;
    }

    const users = await userResponse.json();
    return Array.isArray(users) && users.length > 0 ? users[0] : null;
  } catch (error) {
    console.error('Error in getUserById');
    return null;
  }
}

// Helper: Get user by email using filtered query
async function getUserByEmail(email: string): Promise<any | null> {
  try {
    const userUrl = `${XANO_AUTH_BASE_URL}/user?email=${encodeURIComponent(email)}`;
    const userResponse = await fetch(userUrl);

    if (!userResponse.ok) {
      console.error(`Failed to fetch user by email. Status: ${userResponse.status}`);
      return null;
    }

    const users = await userResponse.json();
    return Array.isArray(users) && users.length > 0 ? users[0] : null;
  } catch (error) {
    console.error('Error in getUserByEmail');
    return null;
  }
}

// Core function: Atomically add credits with locking
async function addCreditsToUserInternal(userId: string, creditAmount: number): Promise<{ success: boolean; newBalance?: number; error?: string; creditsId?: number }> {
  const lockKey = `credit_${userId}`;

  while (creditLocks.has(lockKey)) {
    await creditLocks.get(lockKey);
  }

  let releaseLock: () => void;
  const lockPromise = new Promise<void>((resolve) => { releaseLock = resolve; });
  creditLocks.set(lockKey, lockPromise);

  try {
    // Step 1: Get account_status to find credits_id
    const accountStatusUrl = `${XANO_DATA_BASE_URL}/account_status?user_id=${encodeURIComponent(userId)}`;
    const accountStatusResponse = await fetch(accountStatusUrl);

    if (!accountStatusResponse.ok) {
      return { success: false, error: 'Failed to fetch account status' };
    }

    const accountStatuses = await accountStatusResponse.json();
    const accountStatus = Array.isArray(accountStatuses) && accountStatuses.length > 0
      ? accountStatuses[0]
      : null;

    if (!accountStatus) {
      return { success: false, error: 'No account status found for user' };
    }

    const creditsId = accountStatus.credits_id;

    // Step 2: If user has a credits record, fetch it by ID and validate ownership
    if (creditsId) {
      const creditsResponse = await fetch(`${XANO_DATA_BASE_URL}/credits/${creditsId}`);

      if (!creditsResponse.ok) {
        console.warn(`⚠️  Credits record ${creditsId} not found, creating new record`);
        // Credits record doesn't exist, fall through to create new one
      } else {
        const userCredits = await creditsResponse.json();

        // CRITICAL: Verify the credits record belongs to the current user
        if (userCredits.user_id !== userId) {
          console.error(`❌ SECURITY: Credits record ${creditsId} belongs to user ${userCredits.user_id}, not ${userId}`);
          console.log(`🔧 Creating new credits record for user ${userId} instead`);
          // Fall through to create new record
        } else {
          // Valid credits record for this user - update it
          const newBalance = userCredits.credits + creditAmount;
          console.log(`✅ Valid credits record found. Updating from ${userCredits.credits} to ${newBalance}`);

          await fetch(`${XANO_DATA_BASE_URL}/credits/${creditsId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              credits: newBalance,
              last_refilled: Date.now(),
            }),
          });
          return { success: true, newBalance, creditsId };
        }
      }
    }

    // Step 3: Create new credits record (either no credits_id, or invalid credits_id)
    console.log(`➕ Creating new credits record for user ${userId} with ${creditAmount} credits`);

    const createResponse = await fetch(`${XANO_DATA_BASE_URL}/credits`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: userId,
        credits: creditAmount,
        last_refilled: Date.now(),
      }),
    });

    if (!createResponse.ok) {
      const errorText = await createResponse.text();
      console.error(`❌ Failed to create credits record:`, errorText);
      return { success: false, error: 'Failed to create credits record' };
    }

    const newCredits = await createResponse.json();
    let newCreditsId = newCredits.id;
    console.log(`📋 Initial credits record response:`, newCredits);
    console.log(`📋 Extracted ID from response: ${newCreditsId}`);

    // Verification: Fetch the credits record by user_id to ensure we have the correct ID
    // This is critical because we need to be 100% certain we're linking the right record
    console.log(`🔍 Verifying credits record by fetching with user_id filter...`);
    const verifyCreditsUrl = `${XANO_DATA_BASE_URL}/credits?user_id=${encodeURIComponent(userId)}`;
    const verifyResponse = await fetch(verifyCreditsUrl);

    if (!verifyResponse.ok) {
      console.error(`❌ Failed to verify credits record creation`);
      return { success: false, error: 'Failed to verify credits record after creation' };
    }

    const userCreditsRecords = await verifyResponse.json();
    console.log(`📊 Found ${Array.isArray(userCreditsRecords) ? userCreditsRecords.length : 0} credits records for user ${userId}`);

    // Filter to find the credits record that was just created (highest ID or most recent)
    const filteredCredits = Array.isArray(userCreditsRecords) 
      ? userCreditsRecords.filter((c: any) => c.user_id === userId)
      : [];

    if (filteredCredits.length === 0) {
      console.error(`❌ CRITICAL: Could not find credits record after creation`);
      return { success: false, error: 'Credits record not found after creation' };
    }

    // Use the credits record with the highest ID (most recently created)
    const verifiedCredits = filteredCredits.reduce((latest: any, current: any) => {
      return current.id > latest.id ? current : latest;
    });

    newCreditsId = verifiedCredits.id;
    console.log(`✅ Verified credits record with id: ${newCreditsId}`);
    console.log(`✅ Credits balance: ${verifiedCredits.credits}`);

    // Link the new credits record to account_status
    console.log(`🔗 Linking credits_id ${newCreditsId} to account_status ${accountStatus.id}`);
    console.log(`📤 Sending PATCH request to link credits_id...`);
    console.log(`   URL: ${XANO_DATA_BASE_URL}/account_status/${accountStatus.id}`);
    console.log(`   Payload:`, { credits_id: newCreditsId });

    const linkResponse = await fetch(`${XANO_DATA_BASE_URL}/account_status/${accountStatus.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        credits_id: newCreditsId,
      }),
    });

    console.log(`📥 PATCH Response status: ${linkResponse.status}`);

    if (!linkResponse.ok) {
      const errorText = await linkResponse.text();
      console.error(`❌ CRITICAL ERROR: Failed to link credits to account_status`);
      console.error(`❌ Response status: ${linkResponse.status}`);
      console.error(`❌ Response body:`, errorText);
      console.error(`❌ Attempted to link credits_id ${newCreditsId} to account_status ${accountStatus.id}`);

      // This is CRITICAL - the credits record exists but is orphaned without this link
      // We must return an error to trigger webhook retry or manual intervention
      return { 
        success: false, 
        error: `CRITICAL: Created credits record ${newCreditsId} but failed to link to account_status: ${errorText}` 
      };
    }

    const linkedAccountStatus = await linkResponse.json();
    console.log(`📋 PATCH Response body:`, linkedAccountStatus);
    console.log(`✅ Successfully linked credits_id to account_status`);
    console.log(`✅ Verified credits_id in account_status: ${linkedAccountStatus.credits_id}`);

    // Double-check the link was actually set
    if (linkedAccountStatus.credits_id !== newCreditsId) {
      console.error(`❌ VERIFICATION FAILED: credits_id mismatch after PATCH`);
      console.error(`   Expected: ${newCreditsId}, Got: ${linkedAccountStatus.credits_id}`);
      return {
        success: false,
        error: `CRITICAL: Link verification failed - credits_id not properly set`
      };
    }

    return { success: true, newBalance: creditAmount, creditsId: newCreditsId };
  } catch (error: any) {
    return { success: false, error: error.message };
  } finally {
    creditLocks.delete(lockKey);
    releaseLock!();
  }
}

// Core function: Update account status
async function updateUserAccountStatusInternal(
  userId: string,
  updates: {
    plan_tier?: PlanTier;
    stripe_customer_id?: string;
    subscription_status?: 'active' | 'canceled' | 'past_due' | 'none';
  }
): Promise<{ success: boolean; action?: string; error?: string }> {
  try {
    console.log(`🔍 Updating account status for user_id: ${userId}`);
    console.log(`📝 Updates to apply:`, updates);

    // Query account_status by user_id to find the correct record
    const accountStatusUrl = `${XANO_DATA_BASE_URL}/account_status?user_id=${encodeURIComponent(userId)}`;
    console.log(`🌐 Fetching from: ${accountStatusUrl}`);

    const accountStatusResponse = await fetch(accountStatusUrl);

    if (!accountStatusResponse.ok) {
      console.error(`❌ Failed to fetch account status. Status: ${accountStatusResponse.status}`);
      return { success: false, error: 'Failed to fetch account status' };
    }

    const accountStatuses = await accountStatusResponse.json();
    console.log(`📊 Received ${Array.isArray(accountStatuses) ? accountStatuses.length : 0} account status records from Xano`);

    // Filter to ensure we only get records matching the exact user_id
    const userAccountStatuses = Array.isArray(accountStatuses) 
      ? accountStatuses.filter((status: any) => status.user_id === userId)
      : [];

    console.log(`✅ After filtering by user_id: ${userAccountStatuses.length} records`);

    const accountStatus = userAccountStatuses.length > 0 ? userAccountStatuses[0] : null;

    if (accountStatus) {
      console.log(`📍 Found existing account_status record:`, {
        id: accountStatus.id,
        user_id: accountStatus.user_id,
        current_plan_tier: accountStatus.plan_tier,
        current_subscription_status: accountStatus.subscription_status
      });

      // PATCH the existing record using the account_status id (not user_id)
      const updateUrl = `${XANO_DATA_BASE_URL}/account_status/${accountStatus.id}`;
      console.log(`📤 Patching account_status at: ${updateUrl}`);
      console.log(`📝 Patch payload:`, updates);

      const updateResponse = await fetch(updateUrl, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
      });

      if (!updateResponse.ok) {
        const errorText = await updateResponse.text();
        console.error('❌ Failed to update account_status:', errorText);
        return { success: false, error: `Failed to update account_status: ${errorText}` };
      }

      const updatedRecord = await updateResponse.json();
      console.log(`✅ Successfully updated account_status record:`, {
        id: updatedRecord.id,
        user_id: updatedRecord.user_id,
        new_plan_tier: updatedRecord.plan_tier,
        new_subscription_status: updatedRecord.subscription_status
      });

      return { success: true, action: 'updated' };
    } else {
      console.log(`➕ No existing record found, creating new account_status for user_id: ${userId}`);

      // Create new record with user_id
      const createResponse = await fetch(`${XANO_DATA_BASE_URL}/account_status`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          plan_tier: updates.plan_tier || 'free',
          stripe_customer_id: updates.stripe_customer_id,
          subscription_status: updates.subscription_status || 'none',
        }),
      });

      if (!createResponse.ok) {
        const errorText = await createResponse.text();
        console.error('❌ Failed to create account_status:', errorText);
        return { success: false, error: `Failed to create account_status: ${errorText}` };
      }

      const newRecord = await createResponse.json();
      console.log(`✅ Created new account_status record:`, {
        id: newRecord.id,
        user_id: newRecord.user_id,
        plan_tier: newRecord.plan_tier
      });

      return { success: true, action: 'created' };
    }
  } catch (error: any) {
    console.error('❌ Error in updateUserAccountStatusInternal:', error);
    return { success: false, error: error.message };
  }
}

// Helper: Atomically add credits (wrapper for webhook use)
async function addCreditsToUser(userId: string, creditAmount: number): Promise<void> {
  const result = await addCreditsToUserInternal(userId, creditAmount);
  if (!result.success) {
    console.error('Failed to add credits:', result.error);
  }
}

// Helper: Update account status (wrapper for webhook use)
async function updateUserAccountStatus(
  userId: string,
  updates: {
    plan_tier?: PlanTier;
    stripe_customer_id?: string;
    subscription_status?: 'active' | 'canceled' | 'past_due' | 'none';
  }
): Promise<void> {
  const result = await updateUserAccountStatusInternal(userId, updates);
  if (!result.success) {
    console.error('Failed to update account status:', result.error);
  }
}

export async function registerRoutes(app: Express): Promise<Server> {
  // Internal secured endpoints for webhook operations
  // These endpoints require the INTERNAL_WEBHOOK_SECRET header

  // Internal endpoint: Add credits atomically
  app.post("/api/internal/credits/add", verifyInternalWebhookSecret, async (req, res) => {
    const { userId, creditAmount } = req.body;

    if (!userId || typeof creditAmount !== 'number') {
      return res.status(400).json({ error: 'Missing userId or creditAmount' });
    }

    const result = await addCreditsToUserInternal(userId, creditAmount);

    if (result.success) {
      res.json(result);
    } else {
      res.status(500).json({ error: result.error });
    }
  });

  // Internal endpoint: Update account status
  app.post("/api/internal/account-status/update", verifyInternalWebhookSecret, async (req, res) => {
    const { userId, updates } = req.body;

    if (!userId || !updates) {
      return res.status(400).json({ error: 'Missing userId or updates' });
    }

    const result = await updateUserAccountStatusInternal(userId, updates);

    if (result.success) {
      res.json(result);
    } else {
      res.status(500).json({ error: result.error });
    }
  });

  // Stripe webhook endpoint - raw body middleware applied globally in server/index.ts
  // We need raw body for Stripe signature verification
  // Rate limiting applied to prevent abuse
  app.post("/api/stripe-webhook", webhookRateLimiter, async (req, res) => {
    const sig = req.headers['stripe-signature'];

    if (!sig) {
      console.error('Missing stripe signature');
      return res.status(400).json({ error: 'Missing stripe signature' });
    }

    let event;

    try {
      // Verify the webhook signature - REQUIRED for production
      const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET;
      if (!webhookSecret) {
        console.error('STRIPE_WEBHOOK_SECRET is not configured - rejecting webhook');
        return res.status(500).json({ error: 'Webhook secret not configured' });
      }

      event = stripe.webhooks.constructEvent(req.body, sig, webhookSecret);
    } catch (err: any) {
      console.error('Webhook signature verification failed:', err.message);
      return res.status(400).json({ error: `Webhook Error: ${err.message}` });
    }

    try {
      console.log(`Received webhook event: ${event.type}`);

      // Handle checkout.session.completed - Initial subscription or one-time purchase
      if (event.type === 'checkout.session.completed') {
        const session = event.data.object as Stripe.Checkout.Session;

        console.log(`\n${'='.repeat(80)}`);
        console.log(`🎯 CHECKOUT SESSION COMPLETED`);
        console.log(`Session ID: ${session.id}`);
        console.log(`${'='.repeat(80)}\n`);

        // Idempotency check: Skip if we've already processed this session
        if (processedCheckoutSessions.has(session.id)) {
          console.log(`⏭️  Skipping already processed checkout session: ${session.id}`);
          return res.status(200).json({ received: true, message: 'Session already processed' });
        }

        // Mark as processing immediately to prevent concurrent webhook retries
        processedCheckoutSessions.add(session.id);
        let processingSucceeded = false;

        try {
          const customerId = session.customer as string;
          const clientReferenceId = session.client_reference_id;
          const metadata = session.metadata || {};

          console.log(`📋 Session Details:`);
          console.log(`   Customer ID: ${customerId}`);
          console.log(`   Client Reference ID (User ID): ${clientReferenceId}`);
          console.log(`   Metadata:`, metadata);

          // Use client_reference_id (user ID) directly - no need to query Xano
          // The user must be logged in when they clicked the payment link, which sets this ID
          const userId = clientReferenceId;

          if (!userId) {
            console.error('❌ Missing user ID in checkout session');
            return res.status(400).json({ 
              error: 'User ID not provided', 
              details: 'The checkout session is missing the user ID. Please ensure you are logged in when purchasing.' 
            });
          }

          const purchaseType = metadata.purchase_type;
          const planTier = metadata.plan_tier as PlanTier;
          const creditAmount = metadata.credits ? parseInt(metadata.credits) : 0;

          console.log(`\n📦 Purchase Info:`);
          console.log(`   Type: ${purchaseType}`);
          console.log(`   Plan Tier: ${planTier || 'N/A'}`);
          console.log(`   Credit Amount: ${creditAmount}`);

          // Handle subscription purchase
          if (purchaseType === 'subscription' && planTier) {
            console.log(`\n💳 PROCESSING SUBSCRIPTION`);
            console.log(`   User: ${userId}`);
            console.log(`   Plan: ${planTier}`);

            const result = await updateUserAccountStatusInternal(userId, {
              plan_tier: planTier,
              stripe_customer_id: customerId,
              subscription_status: 'active',
            });

            if (!result.success) {
              console.error('❌ Failed to update account status:', result.error);
              return res.status(500).json({ 
                error: 'Failed to update account', 
                details: result.error 
              });
            }

            console.log(`✅ Account status updated successfully, action: ${result.action}`);

            // Add initial monthly credits for the subscription
            const monthlyCredits = PLAN_LIMITS[planTier]?.monthlyCredits || 0;
            console.log(`\n💰 ADDING SUBSCRIPTION CREDITS`);
            console.log(`   Monthly credits for ${planTier}: ${monthlyCredits}`);

            if (monthlyCredits > 0) {
              console.log(`   Calling addCreditsToUserInternal(${userId}, ${monthlyCredits})...`);
              const creditResult = await addCreditsToUserInternal(userId, monthlyCredits);

              console.log(`💳 Credit addition result:`, {
                success: creditResult.success,
                newBalance: creditResult.newBalance,
                creditsId: creditResult.creditsId,
                error: creditResult.error
              });

              if (!creditResult.success) {
                console.error('❌ CRITICAL: Failed to add subscription credits:', creditResult.error);
                console.error('❌ User will have subscription but NO credits!');
                console.error('❌ Manual intervention required for user:', userId);
                // Don't mark as successfully processed so webhook can retry
                return res.status(500).json({ 
                  error: 'Failed to add credits', 
                  details: creditResult.error 
                });
              }

              console.log(`✅ Credits added successfully!`);
              console.log(`   New balance: ${creditResult.newBalance}`);
              console.log(`   Credits ID: ${creditResult.creditsId}`);
            } else {
              console.log(`⚠️  No monthly credits to add (monthlyCredits = 0)`);
            }
          } else {
            console.log(`\n💵 PROCESSING ONE-TIME PURCHASE`);

            // Handle one-time credit purchase - update customer ID if not set
            if (customerId) {
              console.log(`   Updating customer ID: ${customerId}`);
              await updateUserAccountStatusInternal(userId, {
                stripe_customer_id: customerId,
              });
            }

            // Add credits for one-time purchases ONLY (not for subscriptions)
            if (creditAmount > 0) {
              console.log(`\n💰 ADDING ONE-TIME CREDITS`);
              console.log(`   Credits to add: ${creditAmount}`);
              console.log(`   Calling addCreditsToUserInternal(${userId}, ${creditAmount})...`);

              const creditResult = await addCreditsToUserInternal(userId, creditAmount);

              if (!creditResult.success) {
                console.error('❌ Failed to add credits:', creditResult.error);
                return res.status(500).json({ 
                  error: 'Failed to add credits', 
                  details: creditResult.error 
                });
              }

              console.log(`✅ Credits added successfully!`);
              console.log(`   New balance: ${creditResult.newBalance}`);
              console.log(`   Credits ID: ${creditResult.creditsId}`);
            } else {
              console.log(`⚠️  No credits to add (creditAmount = 0)`);
            }
          }

          // Mark processing as successful
          processingSucceeded = true;
          console.log(`\n✅ CHECKOUT PROCESSING COMPLETE`);
          console.log(`${'='.repeat(80)}\n`);
        } finally {
          // Remove from set if processing failed to allow retry
          // Keep in set if processing succeeded to prevent duplicate processing
          if (!processingSucceeded) {
            console.log(`⚠️  Processing failed, removing from processed set to allow retry`);
            processedCheckoutSessions.delete(session.id);
          }
        }
      }

      // Handle invoice.paid - Monthly subscription renewal ONLY (not initial subscription)
      else if (event.type === 'invoice.paid') {
        const invoice = event.data.object as any;
        const customerId = invoice.customer as string;
        const subscriptionId = invoice.subscription;
        const billingReason = invoice.billing_reason;

        // Skip initial subscription invoices (handled by checkout.session.completed)
        // Only process subscription renewals
        if (billingReason === 'subscription_create') {
          return res.status(200).json({ received: true, message: 'Initial subscription invoice - skipped' });
        }

        // Only process subscription invoices (not one-time payments)
        if (subscriptionId && typeof subscriptionId === 'string') {
          const user = await getUserByStripeCustomerId(customerId);
          if (!user) {
            console.error('User not found for subscription renewal');
            return res.status(404).json({ error: 'User not found' });
          }

          // Get subscription to determine plan tier
          const subscription = await stripe.subscriptions.retrieve(subscriptionId);
          const metadata = subscription.metadata || {};
          const planTier = metadata.plan_tier as PlanTier;

          if (planTier && PLAN_LIMITS[planTier]) {
            const monthlyCredits = PLAN_LIMITS[planTier].monthlyCredits;

            if (monthlyCredits > 0) {
              await addCreditsToUser(user.id, monthlyCredits);
            }
          }
        }
      }

      // Handle invoice.payment_failed - Subscription payment failed
      else if (event.type === 'invoice.payment_failed') {
        const invoice = event.data.object as any;
        const customerId = invoice.customer as string;
        const subscriptionId = invoice.subscription;

        if (subscriptionId && typeof subscriptionId === 'string') {
          const user = await getUserByStripeCustomerId(customerId);
          if (!user) {
            console.error('User not found for payment failure');
            return res.status(404).json({ error: 'User not found' });
          }

          await updateUserAccountStatus(user.id, {
            subscription_status: 'past_due',
          });
        }
      }

      // Handle customer.subscription.deleted - Subscription canceled or expired
      else if (event.type === 'customer.subscription.deleted') {
        const subscription = event.data.object as Stripe.Subscription;
        const customerId = subscription.customer as string;

        const user = await getUserByStripeCustomerId(customerId);
        if (!user) {
          console.error('User not found for subscription cancellation');
          return res.status(404).json({ error: 'User not found' });
        }

        await updateUserAccountStatus(user.id, {
          plan_tier: 'free',
          subscription_status: 'canceled',
        });
      }

      // Handle customer.subscription.updated - Plan change or status update
      else if (event.type === 'customer.subscription.updated') {
        const subscription = event.data.object as Stripe.Subscription;
        const customerId = subscription.customer as string;
        const metadata = subscription.metadata || {};
        const planTier = metadata.plan_tier as PlanTier;

        const user = await getUserByStripeCustomerId(customerId);
        if (!user) {
          console.error('User not found for subscription update');
          return res.status(404).json({ error: 'User not found' });
        }

        // Map Stripe subscription status to our status
        let subscriptionStatus: 'active' | 'canceled' | 'past_due' | 'none' = 'active';
        if (subscription.status === 'canceled' || subscription.status === 'incomplete_expired') {
          subscriptionStatus = 'canceled';
        } else if (subscription.status === 'past_due' || subscription.status === 'unpaid') {
          subscriptionStatus = 'past_due';
        }

        await updateUserAccountStatus(user.id, {
          plan_tier: planTier || undefined,
          subscription_status: subscriptionStatus,
        });
      }

      // Handle invoice.payment_action_required - Payment requires authentication
      else if (event.type === 'invoice.payment_action_required') {
        const invoice = event.data.object as Stripe.Invoice;
        const customerId = invoice.customer as string;

        const user = await getUserByStripeCustomerId(customerId);
        // Payment action required - user will be notified by Stripe
      }

      res.json({ received: true });
    } catch (error: any) {
      console.error('Webhook processing error:', error);
      res.status(500).json({ error: 'Webhook processing failed' });
    }
  });

  // Get current user's credits using server credentials
  app.get("/api/credits/me", requireAuth, async (req, res) => {
    try {
      const userId = req.user?.id;

      if (!userId) {
        return res.status(401).json({ error: 'User not authenticated' });
      }

      console.log(`[DEBUG] Fetching credits for user: ${userId}`);

      // Fetch account_status to get credits_id
      // Use server-side filtering by user_id to get only this user's record
      const accountStatusUrl = `${XANO_DATA_BASE_URL}/account_status?user_id=${encodeURIComponent(userId)}`;
      console.log(`[DEBUG] Fetching account status from: ${accountStatusUrl}`);

      const accountStatusResponse = await fetch(accountStatusUrl);

      if (!accountStatusResponse.ok) {
        console.error('Failed to fetch account status for credits lookup');
        return res.status(500).json({ error: 'Failed to fetch credits' });
      }

      const accountStatuses = await accountStatusResponse.json();
      console.log(`[DEBUG] Received ${Array.isArray(accountStatuses) ? accountStatuses.length : 0} account statuses from Xano`);
      console.log(`[DEBUG] First account status:`, accountStatuses[0]);

      // Filter on server side to ensure only user's account status
      const userAccountStatuses = Array.isArray(accountStatuses) 
        ? accountStatuses.filter((as: any) => as.user_id === userId)
        : [];
      console.log(`[DEBUG] After filtering: ${userAccountStatuses.length} account statuses for user ${userId}`);

      const accountStatus = userAccountStatuses.length > 0 ? userAccountStatuses[0] : null;

      if (!accountStatus) {
        console.log(`[DEBUG] No account status found for user ${userId}, returning default credits`);
        // No account status found - return default credits
        return res.json({
          id: null,
          user_id: userId,
          credits: 0,
          last_spend: null,
          last_refilled: null,
        });
      }

      // Check both credits_id and credit_id for compatibility
      const creditsId = accountStatus.credits_id || accountStatus.credit_id;
      console.log(`[DEBUG] Credits ID from account status: ${creditsId}`);
      console.log(`[DEBUG] Account status fields:`, Object.keys(accountStatus));

      // If user has credits, fetch them
      if (creditsId) {
        const creditsUrl = `${XANO_DATA_BASE_URL}/credits/${creditsId}`;
        console.log(`[DEBUG] Fetching credits from: ${creditsUrl}`);
        
        const creditsResponse = await fetch(creditsUrl);

        if (!creditsResponse.ok) {
          const errorText = await creditsResponse.text();
          console.error(`[DEBUG] Failed to fetch credits record. Status: ${creditsResponse.status}, Response: ${errorText}`);
          
          // If credits record not found, try to create a new one
          if (creditsResponse.status === 404) {
            console.log(`[DEBUG] Credits record not found, creating new one for user ${userId}`);
            
            const createResult = await addCreditsToUserInternal(userId, 0);
            if (createResult.success) {
              console.log(`[DEBUG] Successfully created credits record with balance: ${createResult.newBalance}`);
              
              // Disable caching
              res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
              res.setHeader('Pragma', 'no-cache');
              res.setHeader('Expires', '0');
              
              return res.json({
                id: createResult.creditsId,
                user_id: userId,
                credits: createResult.newBalance,
                last_spend: null,
                last_refilled: Date.now(),
              });
            } else {
              console.error(`[DEBUG] Failed to create credits record: ${createResult.error}`);
              return res.status(500).json({ error: 'Failed to create credits record' });
            }
          }
          
          return res.status(500).json({ error: 'Failed to fetch credits' });
        }

        const userCredits = await creditsResponse.json();
        console.log(`[DEBUG] Fetched credits record:`, userCredits);

        // Verify the credits belong to the correct user
        if (userCredits.user_id !== userId) {
          console.error(`[SECURITY] Credits user_id mismatch! Credits user_id: ${userCredits.user_id}, Expected: ${userId}`);
          return res.status(403).json({ error: 'Unauthorized access to credits' });
        }

        // Disable caching to ensure fresh data
        res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
        res.setHeader('Pragma', 'no-cache');
        res.setHeader('Expires', '0');

        return res.json(userCredits);
      }

      // If no credits record yet, return default
      console.log(`[DEBUG] No credits_id in account status, returning default credits`);

      // Disable caching to ensure fresh data
      res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
      res.setHeader('Pragma', 'no-cache');
      res.setHeader('Expires', '0');

      return res.json({
        id: null,
        user_id: userId,
        credits: 0,
        last_spend: null,
        last_refilled: null,
      });
    } catch (error: any) {
      console.error('Error fetching user credits:', error);
      res.status(500).json({ error: 'Failed to fetch credits' });
    }
  });

  // Upload audio file to S3 (admin only)
  app.post('/api/upload/audio', requireAuth, requireAdmin, upload.single('audio'), async (req, res) => {
    try {
      if (!req.file) {
        return res.status(400).json({ error: 'No audio file provided' });
      }

      // Upload to S3 and get the public URL
      const fileUrl = await uploadAudioToS3(
        req.file.buffer,
        req.file.originalname,
        req.file.mimetype
      );

      res.json({ url: fileUrl, filename: req.file.originalname });
    } catch (error) {
      console.error('Audio upload error:', error);
      res.status(500).json({ error: 'Failed to upload audio file to S3' });
    }
  });

  // Upload cover art to S3 (admin only)
  app.post('/api/upload/cover', requireAuth, requireAdmin, upload.single('cover'), async (req, res) => {
    try {
      if (!req.file) {
        return res.status(400).json({ error: 'No cover image provided' });
      }

      // Upload to S3 and get the public URL
      const fileUrl = await uploadCoverToS3(
        req.file.buffer,
        req.file.originalname,
        req.file.mimetype
      );

      res.json({ url: fileUrl, filename: req.file.originalname });
    } catch (error) {
      console.error('Cover upload error:', error);
      res.status(500).json({ error: 'Failed to upload cover image to S3' });
    }
  });

  // Upload playlist cover to S3 (requires authentication)
  app.post('/api/upload/playlist-cover', requireAuth, upload.single('cover'), async (req, res) => {
    try {
      if (!req.file) {
        return res.status(400).json({ error: 'No cover image provided' });
      }

      // Upload to S3 and get the public URL
      const fileUrl = await uploadPlaylistCoverToS3(
        req.file.buffer,
        req.file.originalname,
        req.file.mimetype
      );

      res.json({ url: fileUrl, filename: req.file.originalname });
    } catch (error) {
      console.error('Playlist cover upload error:', error);
      res.status(500).json({ error: 'Failed to upload playlist cover to S3' });
    }
  });

  // S3 signed URL generation - public endpoint for audio streaming
  app.post("/api/s3/signed-url", async (req, res) => {
    try {
      const { url, expiresIn } = req.body;

      if (!url) {
        return res.status(400).json({ error: 'Missing required field: url' });
      }

      // Extract and validate the S3 key
      let key: string;
      try {
        const parsedUrl = new URL(url);
        key = parsedUrl.pathname.substring(1); // Remove leading slash
      } catch {
        // If not a full URL, treat as a key
        key = url;
      }

      // Validate that the key starts with allowed prefixes
      const isAllowedResource = key.startsWith('audio/') || key.startsWith('covers/') || key.startsWith('playlist-covers/');

      if (!isAllowedResource) {
        return res.status(403).json({ error: 'Access denied: Only audio, cover, and playlist-cover files are allowed' });
      }

      const signedUrl = await generateSignedUrl(url, expiresIn || 3600);
      res.json({ signedUrl });
    } catch (error) {
      console.error('Signed URL generation error:', error);
      res.status(500).json({ error: 'Failed to generate signed URL' });
    }
  });

  // Stripe payment route for one-time credit purchases
  app.post("/api/create-payment-intent", requireAuth, async (req, res) => {
    try {
      const { packageId } = req.body;

      if (!packageId) {
        return res.status(400).json({ error: 'Missing required field: packageId' });
      }

      // Look up the package from our trusted source
      const creditPackage = CREDIT_PACKAGES.find(pkg => pkg.id === packageId);

      if (!creditPackage) {
        return res.status(400).json({ error: 'Invalid package ID' });
      }

      if (!req.user?.id) {
        return res.status(401).json({ error: 'User not authenticated' });
      }

      const paymentIntent = await stripe.paymentIntents.create({
        amount: Math.round(creditPackage.price * 100), // Convert to cents, use server-side price
        currency: "usd",
        automatic_payment_methods: {
          enabled: true,
        },
        metadata: {
          user_id: req.user.id,
          credits: creditPackage.credits.toString(),
          package_id: creditPackage.id,
        },
      });

      res.json({ clientSecret: paymentIntent.client_secret });
    } catch (error: any) {
      console.error('Payment intent error:', error);
      res.status(500).json({ error: "Error creating payment intent: " + error.message });
    }
  });

  // Get current user's account status
  app.get("/api/account-status/me", requireAuth, async (req, res) => {
    try {
      if (!req.user?.id) {
        return res.status(401).json({ error: 'User not authenticated' });
      }

      // Set no-cache headers
      res.set('Cache-Control', 'no-store, no-cache, must-revalidate, private');
      res.set('Pragma', 'no-cache');
      res.set('Expires', '0');

      const accountStatusUrl = `${XANO_DATA_BASE_URL}/account_status?user_id=${encodeURIComponent(req.user.id)}`;
      const accountStatusResponse = await fetch(accountStatusUrl);

      if (!accountStatusResponse.ok) {
        return res.status(500).json({ error: 'Failed to fetch account status' });
      }

      const accountStatuses = await accountStatusResponse.json();
      // Server-side filtering as backup
      const userAccountStatuses = Array.isArray(accountStatuses) 
        ? accountStatuses.filter((status: any) => status.user_id === req.user!.id)
        : [];

      const accountStatus = userAccountStatuses.length > 0 ? userAccountStatuses[0] : null;

      // Return default free tier status if no record exists
      if (!accountStatus) {
        return res.json({
          user_id: req.user.id,
          plan_tier: 'free',
          subscription_status: 'none',
          stripe_customer_id: null,
        });
      }

      res.json(accountStatus);
    } catch (error: any) {
      console.error('Account status error:', error);
      res.status(500).json({ error: "Error fetching account status: " + error.message });
    }
  });

  // Get user's credits by their account_status credits_id
  app.get("/api/credits", requireAuth, async (req, res) => {
    try {
      if (!req.user?.id) {
        return res.status(401).json({ error: 'User not authenticated' });
      }

      // Step 1: Get account_status to find credits_id
      const accountStatusUrl = `${XANO_DATA_BASE_URL}/account_status?user_id=${encodeURIComponent(req.user.id)}`;
      const accountStatusResponse = await fetch(accountStatusUrl);

      if (!accountStatusResponse.ok) {
        return res.status(500).json({ error: 'Failed to fetch account status' });
      }

      const accountStatuses = await accountStatusResponse.json();
      const accountStatus = Array.isArray(accountStatuses) && accountStatuses.length > 0
        ? accountStatuses[0]
        : null;

      // Return default credits if no account status or credits_id exists
      if (!accountStatus || !accountStatus.credits_id) {
        return res.json({
          user_id: req.user.id,
          credits: 0,
          last_refilled: null,
        });
      }

      // Step 2: Fetch user's specific credits record by ID
      const creditsUrl = `${XANO_DATA_BASE_URL}/credits/${accountStatus.credits_id}`;
      const creditsResponse = await fetch(creditsUrl);

      if (!creditsResponse.ok) {
        return res.status(500).json({ error: 'Failed to fetch credits record' });
      }

      const credits = await creditsResponse.json();
      res.json(credits);
    } catch (error: any) {
      console.error('Credits fetch error:', error);
      res.status(500).json({ error: "Error fetching credits: " + error.message });
    }
  });

  // Get single playlist with ownership verification
  app.get("/api/playlists/:id", requireAuth, async (req, res) => {
    try {
      const userId = req.user?.id;
      const playlistId = req.params.id;

      if (!userId) {
        return res.status(401).json({ error: 'User not authenticated' });
      }

      // Fetch the playlist
      const playlistResponse = await fetch(`${XANO_DATA_BASE_URL}/playlist/${playlistId}`);

      if (!playlistResponse.ok) {
        if (playlistResponse.status === 404) {
          return res.status(404).json({ error: 'Playlist not found' });
        }
        return res.status(500).json({ error: 'Failed to fetch playlist' });
      }

      const playlist = await playlistResponse.json();

      // Verify ownership
      if (playlist.user_id !== userId) {
        return res.status(403).json({ error: 'Access denied: You do not own this playlist' });
      }

      res.json(playlist);
    } catch (error: any) {
      console.error('Playlist fetch error:', error);
      res.status(500).json({ error: 'Failed to fetch playlist' });
    }
  });

  // Get current user's playlists with server-side authorization
  app.get("/api/playlists", requireAuth, async (req, res) => {
    try {
      const userId = req.user?.id;

      if (!userId) {
        return res.status(401).json({ error: 'User not authenticated' });
      }

      console.log(`[DEBUG] Fetching playlists for user: ${userId}`);

      // Fetch playlists filtered by user_id
      const playlistsUrl = `${XANO_DATA_BASE_URL}/playlist?user_id=${encodeURIComponent(userId)}`;
      console.log(`[DEBUG] Fetching from: ${playlistsUrl}`);

      const playlistsResponse = await fetch(playlistsUrl);

      if (!playlistsResponse.ok) {
        return res.status(500).json({ error: 'Failed to fetch playlists' });
      }

      const playlists = await playlistsResponse.json();
      console.log(`[DEBUG] Received ${playlists.length} playlists from Xano`);
      console.log(`[DEBUG] First playlist user_id: ${playlists[0]?.user_id}, Expected: ${userId}`);

      // Filter on server side to ensure only user's playlists are returned
      const userPlaylists = playlists.filter((p: any) => p.user_id === userId);
      console.log(`[DEBUG] After filtering: ${userPlaylists.length} playlists for user ${userId}`);

      // Disable caching to ensure fresh data
      res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
      res.setHeader('Pragma', 'no-cache');
      res.setHeader('Expires', '0');

      res.json(userPlaylists);
    } catch (error: any) {
      console.error('Error fetching playlists:', error);
      res.status(500).json({ error: 'Failed to fetch playlists' });
    }
  });

  // Get playlist tracks with ownership verification
  app.get("/api/playlists/:id/tracks", requireAuth, async (req, res) => {
    try {
      const userId = req.user?.id;
      const playlistId = req.params.id;

      if (!userId) {
        return res.status(401).json({ error: 'User not authenticated' });
      }

      console.log(`[DEBUG] Fetching playlist tracks for playlist: ${playlistId}`);

      // First verify playlist ownership
      const playlistResponse = await fetch(`${XANO_DATA_BASE_URL}/playlist/${playlistId}`);

      if (!playlistResponse.ok) {
        if (playlistResponse.status === 404) {
          return res.status(404).json({ error: 'Playlist not found' });
        }
        return res.status(500).json({ error: 'Failed to fetch playlist' });
      }

      const playlist = await playlistResponse.json();

      // Verify ownership
      if (playlist.user_id !== userId) {
        return res.status(403).json({ error: 'Access denied: You do not own this playlist' });
      }

      // Fetch playlist tracks with filter parameter
      const playlistTracksUrl = `${XANO_DATA_BASE_URL}/playlist_track?playlist_id=${encodeURIComponent(playlistId)}`;
      console.log(`[DEBUG] Fetching from: ${playlistTracksUrl}`);

      const playlistTracksResponse = await fetch(playlistTracksUrl);

      if (!playlistTracksResponse.ok) {
        return res.status(500).json({ error: 'Failed to fetch playlist tracks' });
      }

      const allPlaylistTracks = await playlistTracksResponse.json();
      console.log(`[DEBUG] Received ${Array.isArray(allPlaylistTracks) ? allPlaylistTracks.length : 0} playlist tracks from Xano`);

      // Server-side filtering as backup in case Xano query parameter doesn't work
      const filteredTracks = Array.isArray(allPlaylistTracks)
        ? allPlaylistTracks.filter((track: any) => track.playlist_id === playlistId)
        : [];

      console.log(`[DEBUG] After filtering: ${filteredTracks.length} tracks for playlist ${playlistId}`);

      // Disable caching to ensure fresh data
      res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
      res.setHeader('Pragma', 'no-cache');
      res.setHeader('Expires', '0');

      res.json(filteredTracks);
    } catch (error: any) {
      console.error('Playlist tracks fetch error:', error);
      res.status(500).json({ error: 'Failed to fetch playlist tracks' });
    }
  });

  // Get current user's saved tracks with server-side authorization
  app.get("/api/saved-tracks", requireAuth, async (req, res) => {
    try {
      const userId = req.user?.id;

      if (!userId) {
        return res.status(401).json({ error: 'User not authenticated' });
      }

      console.log(`[DEBUG] Fetching saved tracks for user: ${userId}`);

      // Fetch saved tracks filtered by user_id
      const savedTracksUrl = `${XANO_DATA_BASE_URL}/saved_track?user_id=${encodeURIComponent(userId)}`;
      console.log(`[DEBUG] Fetching from: ${savedTracksUrl}`);

      const savedTracksResponse = await fetch(savedTracksUrl);

      if (!savedTracksResponse.ok) {
        return res.status(500).json({ error: 'Failed to fetch saved tracks' });
      }

      const savedTracks = await savedTracksResponse.json();
      console.log(`[DEBUG] Received ${savedTracks.length} saved tracks from Xano`);
      console.log(`[DEBUG] First saved track user_id: ${savedTracks[0]?.user_id}, Expected: ${userId}`);

      // Filter on server side to ensure only user's saved tracks are returned
      const userSavedTracks = savedTracks.filter((st: any) => st.user_id === userId);
      console.log(`[DEBUG] After filtering: ${userSavedTracks.length} saved tracks for user ${userId}`);

      // Disable caching to ensure fresh data
      res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
      res.setHeader('Pragma', 'no-cache');
      res.setHeader('Expires', '0');

      res.json(userSavedTracks);
    } catch (error: any) {
      console.error('Error fetching saved tracks:', error);
      res.status(500).json({ error: 'Failed to fetch saved tracks' });
    }
  });

  // Update playlist with ownership verification
  app.patch("/api/playlists/:id", requireAuth, async (req, res) => {
    try {
      const userId = req.user?.id;
      const playlistId = req.params.id;

      if (!userId) {
        return res.status(401).json({ error: 'User not authenticated' });
      }

      // First verify playlist ownership
      const playlistResponse = await fetch(`${XANO_DATA_BASE_URL}/playlist/${playlistId}`);

      if (!playlistResponse.ok) {
        if (playlistResponse.status === 404) {
          return res.status(404).json({ error: 'Playlist not found' });
        }
        return res.status(500).json({ error: 'Failed to fetch playlist' });
      }

      const playlist = await playlistResponse.json();

      // Verify ownership
      if (playlist.user_id !== userId) {
        return res.status(403).json({ error: 'Access denied: You do not own this playlist' });
      }

      // Sanitize request body - only allow safe fields to be updated
      const { name, description, cover_image_url, privacy, updated_at, is_deleted } = req.body;
      const sanitizedBody: any = {};

      // Whitelist only safe fields that users can update
      if (name !== undefined) sanitizedBody.name = name;
      if (description !== undefined) sanitizedBody.description = description;
      if (cover_image_url !== undefined) sanitizedBody.cover_image_url = cover_image_url;
      if (privacy !== undefined) sanitizedBody.privacy = privacy;
      if (updated_at !== undefined) sanitizedBody.updated_at = updated_at;
      if (is_deleted !== undefined) sanitizedBody.is_deleted = is_deleted;

      // NEVER allow user_id to be changed

      // Update the playlist with sanitized data
      const updateResponse = await fetch(`${XANO_DATA_BASE_URL}/playlist/${playlistId}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(sanitizedBody),
      });

      if (!updateResponse.ok) {
        return res.status(500).json({ error: 'Failed to update playlist' });
      }

      const updatedPlaylist = await updateResponse.json();
      res.json(updatedPlaylist);
    } catch (error: any) {
      console.error('Playlist update error:', error);
      res.status(500).json({ error: 'Failed to update playlist' });
    }
  });

  // Delete playlist with ownership verification
  app.delete("/api/playlists/:id", requireAuth, async (req, res) => {
    try {
      const userId = req.user?.id;
      const playlistId = req.params.id;

      if (!userId) {
        return res.status(401).json({ error: 'User not authenticated' });
      }

      // First verify playlist ownership
      const playlistResponse = await fetch(`${XANO_DATA_BASE_URL}/playlist/${playlistId}`);

      if (!playlistResponse.ok) {
        if (playlistResponse.status === 404) {
          return res.status(404).json({ error: 'Playlist not found' });
        }
        return res.status(500).json({ error: 'Failed to fetch playlist' });
      }

      const playlist = await playlistResponse.json();

      // Verify ownership
      if (playlist.user_id !== userId) {
        return res.status(403).json({ error: 'Access denied: You do not own this playlist' });
      }

      // Delete the playlist
      const deleteResponse = await fetch(`${XANO_DATA_BASE_URL}/playlist/${playlistId}`, {
        method: 'DELETE',
      });

      if (!deleteResponse.ok) {
        return res.status(500).json({ error: 'Failed to delete playlist' });
      }

      res.json({ success: true });
    } catch (error: any) {
      console.error('Playlist delete error:', error);
      res.status(500).json({ error: 'Failed to delete playlist' });
    }
  });

  // Delete playlist track with ownership verification
  app.delete("/api/playlists/:playlistId/tracks/:trackId", requireAuth, async (req, res) => {
    try {
      const userId = req.user?.id;
      const playlistId = req.params.playlistId;
      const playlistTrackId = req.params.trackId;

      if (!userId) {
        return res.status(401).json({ error: 'User not authenticated' });
      }

      // First verify playlist ownership
      const playlistResponse = await fetch(`${XANO_DATA_BASE_URL}/playlist/${playlistId}`);

      if (!playlistResponse.ok) {
        if (playlistResponse.status === 404) {
          return res.status(404).json({ error: 'Playlist not found' });
        }
        return res.status(500).json({ error: 'Failed to fetch playlist' });
      }

      const playlist = await playlistResponse.json();

      // Verify ownership
      if (playlist.user_id !== userId) {
        return res.status(403).json({ error: 'Access denied: You do not own this playlist' });
      }

      // Verify the playlist track belongs to this playlist
      const playlistTrackResponse = await fetch(`${XANO_DATA_BASE_URL}/playlist_track/${playlistTrackId}`);

      if (!playlistTrackResponse.ok) {
        if (playlistTrackResponse.status === 404) {
          return res.status(404).json({ error: 'Playlist track not found' });
        }
        return res.status(500).json({ error: 'Failed to fetch playlist track' });
      }

      const playlistTrack = await playlistTrackResponse.json();

      // Verify the track belongs to the specified playlist
      if (playlistTrack.playlist_id !== playlistId) {
        return res.status(403).json({ error: 'Access denied: This track does not belong to this playlist' });
      }

      // Delete the playlist track
      const deleteResponse = await fetch(`${XANO_DATA_BASE_URL}/playlist_track/${playlistTrackId}`, {
        method: 'DELETE',
      });

      if (!deleteResponse.ok) {
        return res.status(500).json({ error: 'Failed to delete playlist track' });
      }

      res.json({ success: true });
    } catch (error: any) {
      console.error('Playlist track delete error:', error);
      res.status(500).json({ error: 'Failed to delete playlist track' });
    }
  });

  // Create Stripe Customer Portal session for managing subscriptions and payment methods
  app.post("/api/create-billing-portal-session", requireAuth, async (req, res) => {
    try {
      if (!req.user?.id) {
        return res.status(401).json({ error: 'User not authenticated' });
      }

      // Get user's Stripe customer ID from account_status
      const accountStatusUrl = `${XANO_DATA_BASE_URL}/account_status?user_id=${encodeURIComponent(req.user.id)}`;
      const accountStatusResponse = await fetch(accountStatusUrl);

      if (!accountStatusResponse.ok) {
        return res.status(500).json({ error: 'Failed to fetch account status' });
      }

      const accountStatuses = await accountStatusResponse.json();
      const accountStatus = Array.isArray(accountStatuses) && accountStatuses.length > 0
        ? accountStatuses[0]
        : null;

      if (!accountStatus?.stripe_customer_id) {
        return res.status(404).json({ error: 'No active subscription found. Please subscribe first.' });
      }

      // Create billing portal session
      const session = await stripe.billingPortal.sessions.create({
        customer: accountStatus.stripe_customer_id,
        return_url: `${req.protocol}://${req.get('host')}/profile`,
      });

      res.json({ url: session.url });
    } catch (error: any) {
      console.error('Billing portal session error:', error);
      res.status(500).json({ error: "Error creating billing portal session: " + error.message });
    }
  });


  const httpServer = createServer(app);

  return httpServer;
}