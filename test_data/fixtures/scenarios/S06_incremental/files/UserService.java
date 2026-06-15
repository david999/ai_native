package com.example.demo.service;

import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class UserService {

    public String getDisplayName(Optional<String> nickname) {
        // BUG: orElse(null) then direct use may NPE downstream
        String name = nickname.orElse(null);
        // aicr incremental marker
        return name.trim();
    }
}
