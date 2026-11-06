package expendable

import "testing"

// 친구 이름 OCR 은 이름 누락("#6338")이나 뒤쪽 배지 잡음("Jeb#633813", "Jeb#6338I3")이 섞인다.
// match_anywhere + #UID key 로 같은 친구를 다시 고르지 않는지 확인한다.
func TestWithBlacklistMatchAnywhere(t *testing.T) {
	// 패턴은 MaaFramework(C++) 정규식에서 쓰이며 Go regexp 는 lookahead 를 지원하지 않으므로 문자열로 비교한다.
	patterns := withBlacklist([]string{".*#.*"}, []string{"#6338", "#8720"}, true, true)
	want := "^(?!.*(?:#6338|#8720)).*#.*"
	if len(patterns) != 1 || patterns[0] != want {
		t.Fatalf("got %q want %q", patterns, want)
	}
	if got := stripBlacklistPrefix(patterns[0], true); got != ".*#.*" {
		t.Errorf("strip anywhere prefix: got %q", got)
	}
}

func TestWithBlacklistAnchoredUnchanged(t *testing.T) {
	patterns := withBlacklist([]string{".+"}, []string{"abc)"}, true, false)
	want := "^(?!(?:abc\\))" + trailingNoiseSuffix + "$).+"
	if patterns[0] != want {
		t.Fatalf("got %q want %q", patterns[0], want)
	}
	if got := stripBlacklistPrefix(patterns[0], true); got != ".+" {
		t.Errorf("strip anchored prefix: got %q", got)
	}
}

func TestApplyKeyRegexFriendTag(t *testing.T) {
	for text, want := range map[string]string{
		"Jeb#633813":  "#6338",
		"Jeb#6338I3":  "#6338",
		"#6338":       "#6338",
		"(별칭)카인#8720": "#8720",
	} {
		got, err := applyKeyRegex(text, `(\#\d{4})`)
		if err != nil || got != want {
			t.Errorf("applyKeyRegex(%q) = %q, %v; want %q", text, got, err, want)
		}
	}
}
