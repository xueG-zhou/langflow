package org.langflow.sdk.v1;

import org.langflow.sdk.LangflowException;
import org.langflow.sdk.v1.model.V1Models.RunResponse;

import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

/** A non-blocking flow run with status, cancellation, and bounded waiting helpers. */
public final class BackgroundJob {
    private final CompletableFuture<RunResponse> future;

    BackgroundJob(CompletableFuture<RunResponse> future) {
        this.future = future;
    }

    public boolean isRunning() { return !future.isDone(); }
    public boolean isCompleted() { return future.isDone() && !future.isCompletedExceptionally() && !future.isCancelled(); }
    public boolean isFailed() { return future.isCompletedExceptionally() || future.isCancelled(); }
    public CompletableFuture<RunResponse> future() { return future; }

    public RunResponse waitForCompletion() {
        return join();
    }

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
