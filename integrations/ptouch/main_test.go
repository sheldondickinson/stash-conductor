package main

import (
	"context"
	"errors"
	pt "github.com/crmin/ptouch-go"
	"strings"
	"testing"
	"time"
)

func TestNoDataIsFailedAndPartialDataNeverRetries(t *testing.T) {
	device := &pt.PrinterStatusError{Status: pt.Status{Type: pt.StatusError, ErrorInfo2: 4}}
	for _, tc := range []struct {
		sent       int
		completion pt.Completion
		want       string
	}{
		{0, pt.Indeterminate, "failed"}, {1, pt.Failed, "outcome_unknown"},
		{100, pt.SentUnconfirmed, "sent_unconfirmed"}, {100, pt.Completed, "outcome_unknown"},
	} {
		state, detail := printOutcome(pt.JobResult{BytesSent: tc.sent, Completion: tc.completion}, device)
		if state != tc.want {
			t.Fatalf("%+v: %s", tc, state)
		}
		if !strings.Contains(detail, "00/04") {
			t.Fatal("Undocumented device code was hidden:", detail)
		}
	}
	state, _ := printOutcome(pt.JobResult{BytesSent: 100, Completion: pt.Completed}, nil)
	if state != "completed" {
		t.Fatal(state)
	}
}

func TestKnownAndUnrecognisedDeviceErrorsStayVisible(t *testing.T) {
	if statusProblem(pt.Status{}) != "" {
		t.Fatal("Healthy status marked as error")
	}
	if !strings.Contains(statusProblem(pt.Status{Errors: []pt.PrinterError{pt.ErrorCoverOpen}}), "cover open") {
		t.Fatal("Known error missing")
	}
	if statusProblem(pt.Status{ErrorInfo2: 4}) == "" {
		t.Fatal("Unknown error bit ignored")
	}
}

type fakeStatus struct{ calls int }

func (f *fakeStatus) Snapshot(context.Context) (pt.StatusObservation, error) {
	f.calls++
	return pt.StatusObservation{}, nil
}
func (f *fakeStatus) Next(ctx context.Context) (pt.StatusObservation, error) { return f.Snapshot(ctx) }
func (f *fakeStatus) Close() error                                           { return nil }

func TestSNMPPollingIsBoundedAndCancellable(t *testing.T) {
	f := &fakeStatus{}
	p := &pacedStatus{StatusProvider: f, interval: 30 * time.Millisecond}
	p.Snapshot(context.Background())
	start := time.Now()
	p.Next(context.Background())
	if time.Since(start) < p.interval {
		t.Fatal("Polling was not paced")
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err := p.Next(ctx); !errors.Is(err, context.Canceled) {
		t.Fatal(err)
	}
	if f.calls != 2 {
		t.Fatal("Cancelled poll reached device")
	}
}
