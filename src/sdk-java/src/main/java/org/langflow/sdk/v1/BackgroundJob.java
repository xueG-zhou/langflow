package org.langflow.sdk.v1;

import org.langflow.sdk.LangflowException;
import org.langflow.sdk.v1.model.V1Models.RunResponse;

import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

/**
 * Handle for one non-blocking v1 flow execution.
 *
 * <p>The handle is safe to inspect from multiple threads. Cancellation is
 * propagated to the underlying OkHttp call. A wait timeout does not cancel the
 * run, allowing the caller to wait again or observe the future later.</p>
 */
public final class BackgroundJob {
    private final CompletableFuture<RunResponse> future;

    BackgroundJob(CompletableFuture<RunResponse> future) {
        this.future = future;
    }

    /** Returns {@code true} while the HTTP request has not reached a terminal state. */
    public boolean isRunning() { return !future.isDone(); }
    /** Returns {@code true} only after a successful response has been decoded. */
    public boolean isCompleted() { return future.isDone() && !future.isCompletedExceptionally() && !future.isCancelled(); }
    /** Returns {@code true} after cancellation or exceptional completion. */
    public boolean isFailed() { return future.isCompletedExceptionally() || future.isCancelled(); }
    /** Exposes the underlying future for composition with application async pipelines. */
    public CompletableFuture<RunResponse> future() { return future; }

    /** Blocks indefinitely until the run completes or fails. */
    public RunResponse waitForCompletion() {
        return join();
    }

    /**
     * Waits up to the supplied duration without cancelling the run on timeout.
     *
     * @throws org.langflow.sdk.TimeoutException when the duration elapses
     */
    public RunResponse waitForCompletion(Duration timeout) {
        if (timeout == null) return join();
        try {
            return future.get(timeout.toMillis(), TimeUnit.MILLISECONDS);
        } catch (TimeoutException e) {
            throw new org.langflow.sdk.TimeoutException(
                    "Langflow background run did not complete within " + timeout, e);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new LangflowException("Interrupted while waiting for Langflow background run", e);
        } catch (ExecutionException e) {
            throw propagate(e.getCause());
        }
    }

    /** Cancels a running request; returns false when it was already terminal. */
    public boolean cancel() { return !future.isDone() && future.cancel(true); }

    private RunResponse join() {
        try {
            return future.get();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new LangflowException("Interrupted while waiting for Langflow background run", e);
        } catch (ExecutionException e) {
            throw propagate(e.getCause());
        }
    }

    private RuntimeException propagate(Throwable cause) {
        return cause instanceof RuntimeException runtime ? runtime
                : new LangflowException("Langflow background run failed", cause);
    }
}
